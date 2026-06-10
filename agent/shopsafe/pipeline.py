"""ShopSafe pipeline orchestrator: Planner → Researcher → Verdict → Auditor → Loop."""

from __future__ import annotations

import asyncio
from typing import Callable, List, Optional

from pydantic import BaseModel, Field

from shopsafe.config import get_config
from shopsafe.llm import generate_structured
from shopsafe.models import AuditVerdict, ResearchPlan, SafetyVerdict
from shopsafe.prompt import shopsafe_planner_instruction, shopsafe_verdict_instruction
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
    return await generate_structured(
        agent_name="shopsafe_planner",
        instruction=shopsafe_planner_instruction,
        user_content=content,
        schema=ResearchPlan,
        model=get_config().planner_model,
    )


async def _execute_research(plan: ResearchPlan) -> str:
    """Run all planned queries in parallel and join into one evidence-pool string."""
    async def _one(pq) -> str:
        return await search(
            pq.query,
            None,
            include_domains=pq.include_domains or None,
            category=pq.category,
        )

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


async def run_pipeline(
    user_text: str,
    *,
    on_stage: Optional[Callable[[str], None]] = None,
) -> PipelineResult:
    """Run the full ShopSafe pipeline and return a PipelineResult."""
    from shopsafe.judge import run_groundedness_audit

    cfg = get_config()

    def _stage(msg: str) -> None:
        if on_stage:
            on_stage(msg)

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
            plan = await _plan_research(
                user_text,
                critique=critique,
                prior_queries=prior_queries if pass_num > 1 else None,
            )
            plans.append(plan)
            prior_queries.extend(pq.query for pq in plan.queries)

            _stage(f"[PASS {pass_num}] RESEARCHING ({len(plan.queries)} queries in parallel)")
            new_evidence = await _execute_research(plan)
            evidence_pool = (evidence_pool + "\n\n" + new_evidence).strip() if evidence_pool else new_evidence

            _stage(f"[PASS {pass_num}] WRITING VERDICT")
            verdict = await _write_verdict(
                user_text,
                plan,
                evidence_pool,
                critique=critique,
            )
            verdict = _enforce_evidence_floor(verdict)

            if pass_num == 1:
                session.pass1_verdict = verdict
            else:
                session.pass2_verdict = verdict

            _stage(f"[PASS {pass_num}] AUDITING")
            audit = await run_groundedness_audit()
            audits.append(audit)
            candidates.append((verdict, audit))

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
