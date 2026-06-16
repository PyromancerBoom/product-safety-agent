"""ShopSafe pipeline orchestrator: Planner → Researcher → Verdict → Auditor → Loop."""

from __future__ import annotations

import asyncio
from typing import Callable, List, Optional

from pydantic import BaseModel, Field

from shopsafe.config import get_config
from shopsafe.llm import generate_structured
from shopsafe.models import AuditVerdict, ResearchPlan, SafetyVerdict
from shopsafe.prompt import load_playbook, shopsafe_planner_instruction, shopsafe_verdict_instruction
from shopsafe.session import AgentSessionState, session_scope
from shopsafe.tools.search import search


class PipelineResult(BaseModel):
    final_verdict: SafetyVerdict
    final_audit: Optional[AuditVerdict] = None
    approved: bool = False
    plans: List[ResearchPlan] = Field(default_factory=list)
    audits: List[AuditVerdict] = Field(default_factory=list)
    passes_used: int = 1


def _enforce_evidence_floor(verdict: SafetyVerdict) -> SafetyVerdict:
    """Downgrade any 'safe' ingredient that cites no sources to 'caution'.

    Deterministic enforcement of the product's trust rule: a clean bill of health
    must be backed by at least one cited claim, never asserted on faith. Runs
    before the verdict is audited so the judge sees the corrected form.
    """
    for ing in verdict.ingredients:
        if ing.verdict == "safe" and not ing.claims:
            ing.verdict = "caution"
            ing.reason = f"Limited cited evidence — {ing.reason}"
    return verdict


def _select_best(
    candidates: list[tuple[SafetyVerdict, AuditVerdict]],
    threshold: float,
) -> tuple[SafetyVerdict, AuditVerdict]:
    """Pick the strongest (verdict, audit) across passes — never just the last.

    Prefers verdicts that clear the audit threshold; among the eligible pool,
    the highest mean audit score wins. Guarantees refinement cannot regress the
    final answer.
    """
    passing = [c for c in candidates if c[1].meets(threshold)]
    pool = passing or candidates
    return max(pool, key=lambda c: c[1].mean_score)


async def _plan_research(
    user_text: str,
    *,
    critique: str | None = None,
    prior_queries: list[str] | None = None,
) -> ResearchPlan:
    cfg = get_config()
    if critique:
        prior_block = "\n".join(f"- {q}" for q in (prior_queries or []))
        content = (
            f"User Query: {user_text}\n\n"
            f"Auditor Critique:\n{critique}\n\n"
            f"Queries already run (do NOT duplicate):\n{prior_block or '(none)'}\n\n"
            f"Emit {cfg.max_planned_queries} NEW queries that address the critique."
        )
    else:
        content = (
            f"User Query: {user_text}\n\n"
            f"Emit {cfg.max_planned_queries} targeted search queries."
        )
    
    instruction = shopsafe_planner_instruction
    pb = load_playbook()
    if pb:
        instruction += f"\n\n## Learned playbook (from past low-scoring runs)\n{pb}"

    return await generate_structured(
        agent_name="shopsafe_planner",
        instruction=instruction,
        user_content=content,
        schema=ResearchPlan,
        model=get_config().planner_model,
    )


async def _execute_research(
    plan: ResearchPlan,
    *,
    emit: Callable[[str, dict], None] | None = None,
    pass_num: int = 1,
) -> str:
    """Run all planned queries in parallel and join into one evidence-pool string."""
    async def _one(pq) -> str:
        result = await search(
            pq.query,
            None,
            include_domains=pq.include_domains or None,
            category=pq.category,
        )
        if emit:
            # One "URL:" line per formatted result block — cheap source count for the UI.
            emit("search_done", {
                "pass": pass_num,
                "query": pq.query,
                "purpose": pq.purpose,
                "sources": result.count("URL: "),
            })
        return result

    results = await asyncio.gather(*[_one(pq) for pq in plan.queries])

    blocks = []
    for pq, result in zip(plan.queries, results):
        blocks.append(
            f"--- Query: {pq.query} ---\n"
            f"Purpose: {pq.purpose}\n"
            f"{result}"
        )
    return "\n\n".join(blocks)


async def _write_verdict(
    user_text: str,
    plan: ResearchPlan,
    evidence_pool: str,
    *,
    critique: str | None = None,
) -> SafetyVerdict:
    cfg = get_config()
    critique_block = f"\nCritique from previous pass:\n{critique}\n" if critique else ""
    content = (
        f"User Query: {user_text}\n\n"
        f"Research Plan:\n"
        f"  Product: {plan.product_name}\n"
        f"  Ingredients to check: {', '.join(plan.ingredients_to_check)}\n"
        f"  User context: {plan.user_context or 'none'}\n"
        f"{critique_block}\n"
        f"Evidence Pool:\n{evidence_pool}"
    )
    return await generate_structured(
        agent_name="shopsafe_verdict_writer",
        instruction=shopsafe_verdict_instruction,
        user_content=content,
        schema=SafetyVerdict,
        model=cfg.verdict_model,
    )


def _annotate_audit(span, audit, pass_num: int) -> None:
    """Attach the three audit scores as attributes and Phoenix annotations to the active span."""
    if not span or not hasattr(span, "is_recording") or not span.is_recording():
        return
        
    try:
        span.set_attributes({
            "shopsafe.audit.groundedness": audit.groundedness_score,
            "shopsafe.audit.authority": audit.authority_score,
            "shopsafe.audit.tone_safety": audit.tone_safety_score,
            "shopsafe.audit.mean": audit.mean_score,
            "shopsafe.audit.pass": pass_num,
            "shopsafe.audit.approved": audit.is_approved,
        })
    except Exception as e:
        print(f"Warning: Failed to set OTEL span attributes: {e}")

    try:
        from phoenix.client import Client
        px_client = Client()
        span_id_hex = format(span.get_span_context().span_id, "016x")

        for name, score in (
            ("shopsafe.audit.groundedness", audit.groundedness_score),
            ("shopsafe.audit.authority", audit.authority_score),
            ("shopsafe.audit.tone_safety", audit.tone_safety_score),
        ):
            px_client.spans.add_span_annotation(
                span_id=span_id_hex,
                annotation_name=name,
                annotator_kind="LLM",
                score=score,
            )
    except Exception:
        pass


async def run_pipeline(
    user_text: str,
    *,
    on_stage: Optional[Callable[[str], None]] = None,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> PipelineResult:
    """Run the full ShopSafe pipeline and return a PipelineResult.

    `on_stage` receives human-readable banner strings (CLI use).
    `on_event` receives structured (kind, payload) events (web UI / SSE use).
    Both are optional and failure-isolated — a broken callback never kills a run.
    """
    from shopsafe.judge import run_groundedness_audit

    cfg = get_config()

    def _stage(msg: str) -> None:
        if on_stage:
            on_stage(msg)

    def _emit(kind: str, payload: dict) -> None:
        if on_event:
            try:
                on_event(kind, payload)
            except Exception:
                pass

    session = AgentSessionState(user_query=user_text)
    plans: list[ResearchPlan] = []
    audits: list[AuditVerdict] = []
    candidates: list[tuple[SafetyVerdict, AuditVerdict]] = []
    prior_queries: list[str] = []
    evidence_pool = ""

    async with session_scope(session):
        for pass_num in range(1, cfg.max_refinement_passes + 1):
            critique = audits[-1].critique if audits else None

            _stage(f"[PASS {pass_num}] PLANNING")
            _emit("stage", {"pass": pass_num, "stage": "planning", "critique": critique})
            plan = await _plan_research(
                user_text,
                critique=critique,
                prior_queries=prior_queries if pass_num > 1 else None,
            )
            plans.append(plan)
            prior_queries.extend(pq.query for pq in plan.queries)
            _emit("plan", {"pass": pass_num, **plan.model_dump()})

            _stage(f"[PASS {pass_num}] RESEARCHING ({len(plan.queries)} queries in parallel)")
            _emit("stage", {"pass": pass_num, "stage": "researching", "queries": len(plan.queries)})
            new_evidence = await _execute_research(plan, emit=_emit, pass_num=pass_num)
            evidence_pool = (evidence_pool + "\n\n" + new_evidence).strip() if evidence_pool else new_evidence

            _stage(f"[PASS {pass_num}] WRITING VERDICT")
            _emit("stage", {"pass": pass_num, "stage": "writing"})
            verdict = await _write_verdict(
                user_text,
                plan,
                evidence_pool,
                critique=critique,
            )
            verdict = _enforce_evidence_floor(verdict)
            _emit("verdict", {"pass": pass_num, **verdict.model_dump()})

            if pass_num == 1:
                session.pass1_verdict = verdict
            else:
                session.pass2_verdict = verdict

            _stage(f"[PASS {pass_num}] AUDITING")
            _emit("stage", {"pass": pass_num, "stage": "auditing"})
            audit = await run_groundedness_audit()
            audits.append(audit)
            candidates.append((verdict, audit))
            _emit("audit", {
                "pass": pass_num,
                **audit.model_dump(),
                "mean": audit.mean_score,
                "passed": audit.meets(cfg.audit_pass_threshold),
                "threshold": cfg.audit_pass_threshold,
            })

            # Annotate audit scores onto the span
            from opentelemetry import trace as _otel_trace
            try:
                span = _otel_trace.get_current_span()
                _annotate_audit(span, audit, pass_num)
            except Exception:
                pass

            # Deterministic gate: all dimensions must clear the threshold. We do
            # NOT trust audit.is_approved — the model frequently sets it false even
            # when its own scores pass.
            if audit.meets(cfg.audit_pass_threshold):
                break
            if pass_num == cfg.max_refinement_passes:
                break

    # Return the strongest verdict across all passes, never merely the last one.
    best_verdict, best_audit = _select_best(candidates, cfg.audit_pass_threshold)
    return PipelineResult(
        final_verdict=best_verdict,
        final_audit=best_audit,
        approved=best_audit.meets(cfg.audit_pass_threshold),
        plans=plans,
        audits=audits,
        passes_used=len(plans),
    )
