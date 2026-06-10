"""Offline verification script for session state and pipeline flow (Open-Core)."""

import asyncio
import random
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shopsafe.session import (
    AgentSessionState,
    get_current_session,
    log_search,
    session_scope,
)
from shopsafe.models import AuditVerdict, ResearchPlan, SafetyVerdict, PlannedQuery


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_safety_verdict(verdict: str = "caution", reason: str = "Test.") -> SafetyVerdict:
    return SafetyVerdict(
        product_name="retinol",
        overall_verdict=verdict,
        overall_reason=reason,
        user_context_notes="No specific user context provided.",
        ingredients=[],
    )


def _make_research_plan() -> ResearchPlan:
    return ResearchPlan(
        product_name="retinol",
        ingredients_to_check=["retinol"],
        user_context="",
        queries=[
            PlannedQuery(
                query="retinol safety FDA",
                category=None,
                include_domains=["fda.gov"],
                purpose="Check FDA regulatory stance on retinol",
            )
        ],
    )


def _make_audit(approved: bool, critique: str = "") -> AuditVerdict:
    return AuditVerdict(
        is_approved=approved,
        groundedness_score=0.90 if approved else 0.60,
        authority_score=0.90 if approved else 0.55,
        tone_safety_score=0.90 if approved else 0.75,
        critique=critique,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

async def test_session_isolation():
    print("--- Running Test: Session Context Isolation ---")

    async def worker(worker_id: int, query: str):
        state = AgentSessionState(user_query=query)
        async with session_scope(state):
            current = get_current_session()
            assert current is not None
            assert current.user_query == query
            assert len(current.search_history) == 0

            log_search(f"query_{worker_id}_1", f"results_{worker_id}_1")
            await asyncio.sleep(random.uniform(0.01, 0.05))

            current = get_current_session()
            assert len(current.search_history) == 1
            assert current.search_history[0].query == f"query_{worker_id}_1"

            log_search(f"query_{worker_id}_2", f"results_{worker_id}_2")
            await asyncio.sleep(random.uniform(0.01, 0.05))

            current = get_current_session()
            assert len(current.search_history) == 2
            assert current.search_history[1].query == f"query_{worker_id}_2"

            print(f"[SUCCESS] Worker {worker_id} (query='{query}') isolated correctly.")

    await asyncio.gather(
        worker(1, "retinol"),
        worker(2, "benzene"),
        worker(3, "salicylic acid"),
    )
    print("--- Session Context Isolation Test Passed ---\n")


async def test_session_state_updates():
    print("--- Running Test: Session State Updates ---")

    state = AgentSessionState(user_query="retinol")
    async with session_scope(state):
        # Simulate pipeline writing pass1 verdict
        state.pass1_verdict = _make_safety_verdict("caution", "Thin sources.")
        assert state.pass1_verdict is not None
        assert state.pass2_verdict is None
        print("[SUCCESS] Pass 1 verdict stored correctly.")

        state.critique = "Search PubMed for retinol toxicity."
        state.pass2_verdict = _make_safety_verdict("safe", "Better sources after critique.")
        assert state.pass2_verdict is not None
        assert state.pass2_verdict.overall_verdict == "safe"
        print("[SUCCESS] Pass 2 verdict and critique stored correctly.")

    # After context exits, session var is reset
    assert get_current_session() is None
    print("[SUCCESS] Session cleared after context exit.")
    print("--- Session State Updates Test Passed ---\n")


async def test_mocked_judge_audit():
    print("--- Running Test: Groundedness Auditor ---")

    audit_result = _make_audit(False, critique="Need higher authority sources.")

    with patch("shopsafe.judge.generate_structured", new=AsyncMock(return_value=audit_result)):
        from shopsafe.judge import run_groundedness_audit

        state = AgentSessionState(user_query="retinol")
        state.pass1_verdict = _make_safety_verdict()
        log_search("retinol safety", "some snippet")

        async with session_scope(state):
            audit = await run_groundedness_audit()
            assert audit.is_approved is False
            assert audit.groundedness_score == 0.60
            assert audit.critique == "Need higher authority sources."
            print("[SUCCESS] Groundedness auditor returned correct AuditVerdict.")

    print("--- Groundedness Auditor Test Passed ---\n")


async def test_mocked_pipeline_single_pass():
    print("--- Running Test: Pipeline — approved on Pass 1 ---")

    plan = _make_research_plan()
    verdict = _make_safety_verdict("safe", "Sufficient evidence.")
    audit = _make_audit(True)

    call_results = [plan, verdict, audit]
    call_idx = 0

    async def fake_generate_structured(**kwargs):
        nonlocal call_idx
        result = call_results[call_idx]
        call_idx += 1
        return result

    async def fake_search(query, tool_context, **kwargs):
        log_search(query, f"Mock results for: {query}")
        return f"Mock results for: {query}"

    with patch("shopsafe.pipeline.generate_structured", new=fake_generate_structured), \
         patch("shopsafe.pipeline.search", new=fake_search), \
         patch("shopsafe.judge.generate_structured", new=fake_generate_structured):
        from shopsafe.pipeline import run_pipeline
        result = await run_pipeline("retinol safety")

    assert result.passes_used == 1
    assert result.final_verdict.overall_verdict == "safe"
    assert len(result.plans) == 1
    assert len(result.audits) == 1
    print("[SUCCESS] Pipeline completed in 1 pass when auditor approves.")
    print("--- Pipeline Single-Pass Test Passed ---\n")


async def test_mocked_pipeline_two_pass():
    print("--- Running Test: Pipeline — rejected on Pass 1, approved on Pass 2 ---")

    plan1 = _make_research_plan()
    verdict1 = _make_safety_verdict("caution", "Thin sources.")
    audit1 = _make_audit(False, critique="Search PubMed for retinol toxicity.")
    plan2 = _make_research_plan()
    verdict2 = _make_safety_verdict("safe", "Better sources after critique.")
    audit2 = _make_audit(True)

    call_results = [plan1, verdict1, audit1, plan2, verdict2, audit2]
    call_idx = 0

    async def fake_generate_structured(**kwargs):
        nonlocal call_idx
        result = call_results[call_idx]
        call_idx += 1
        return result

    async def fake_search(query, tool_context, **kwargs):
        log_search(query, f"Mock results for: {query}")
        return f"Mock results for: {query}"

    with patch("shopsafe.pipeline.generate_structured", new=fake_generate_structured), \
         patch("shopsafe.pipeline.search", new=fake_search), \
         patch("shopsafe.judge.generate_structured", new=fake_generate_structured):
        from shopsafe.pipeline import run_pipeline
        result = await run_pipeline("retinol safety")

    assert result.passes_used == 2
    assert result.final_verdict.overall_verdict == "safe"
    assert len(result.plans) == 2
    assert len(result.audits) == 2
    print("[SUCCESS] Pipeline ran 2 passes when Pass 1 audit rejected.")
    print("--- Pipeline Two-Pass Test Passed ---\n")


async def main():
    await test_session_isolation()
    await test_session_state_updates()
    await test_mocked_judge_audit()
    await test_mocked_pipeline_single_pass()
    await test_mocked_pipeline_two_pass()
    print("All offline tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
