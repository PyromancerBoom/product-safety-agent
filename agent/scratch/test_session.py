"""Offline verification script for checking session state, critic, and multi-pass loop updates (Open-Core)."""

import asyncio
import random
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the parent directory is in sys.path so we can import from agent package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shopsafe.session import (
    AgentSessionState,
    session_scope,
    get_current_session,
    log_search,
)
from shopsafe.models import SafetyVerdict, AuditVerdict
from shopsafe.agent import run_safety_check_pass
from shopsafe.judge import run_groundedness_audit


@contextmanager
def mock_runner_context(mock_runner):
    """Context manager to patch InMemoryRunner across all namespaces where it is used."""
    with patch("google.adk.runners.InMemoryRunner", return_value=mock_runner) as p1, \
         patch("shopsafe.judge.InMemoryRunner", return_value=mock_runner) as p2, \
         patch("shopsafe.agent.InMemoryRunner", return_value=mock_runner, create=True) as p3:
        yield (p1, p2, p3)


async def test_session_isolation():
    print("--- Running Test: Session Context Isolation ---")

    async def worker(worker_id: int, query: str):
        # Create a unique session state for this concurrent worker
        state = AgentSessionState(user_query=query)
        async with session_scope(state):
            # Verify we are starting in the correct, isolated session
            current = get_current_session()
            assert current is not None
            assert current.user_query == query
            assert len(current.search_history) == 0

            # Simulate first search with a random delay to interleave tasks
            log_search(f"query_{worker_id}_1", f"results_{worker_id}_1")
            await asyncio.sleep(random.uniform(0.01, 0.05))

            # Verify no crosstalk occurred
            current = get_current_session()
            assert len(current.search_history) == 1
            assert current.search_history[0].query == f"query_{worker_id}_1"

            # Simulate second search
            log_search(f"query_{worker_id}_2", f"results_{worker_id}_2")
            await asyncio.sleep(random.uniform(0.01, 0.05))

            # Verify both search records are present and correct in this worker's context
            current = get_current_session()
            assert len(current.search_history) == 2
            assert current.search_history[0].query == f"query_{worker_id}_1"
            assert current.search_history[1].query == f"query_{worker_id}_2"

            print(f"[SUCCESS] Worker {worker_id} (query='{query}') isolated correctly.")

    # Run multiple concurrent workers to test interleaving task isolation
    await asyncio.gather(
        worker(1, "retinol"),
        worker(2, "benzene"),
        worker(3, "salicylic acid"),
    )
    print("--- Session Context Isolation Test Passed ---\n")


async def test_mocked_run_pass():
    print("--- Running Test: Programmatic Runner & State Updates ---")

    dummy_json_pass1 = (
        '{"product_name": "retinol", "overall_verdict": "caution", '
        '"overall_reason": "Thin search evidence.", "ingredients": []}'
    )

    mock_part = MagicMock()
    mock_part.text = dummy_json_pass1
    mock_part.function_call = None
    mock_part.function_response = None

    mock_event = MagicMock()
    mock_event.content.parts = [mock_part]

    # Mock async generator representing runner.run_async response streams
    async def mock_run_async(*args, **kwargs):
        yield mock_event

    mock_runner = MagicMock()
    mock_runner.session_service.create_session = AsyncMock()
    mock_runner.run_async = mock_run_async

    with mock_runner_context(mock_runner):
        # Case 1: Run safety check pass. It should create its own temporary session.
        verdict = await run_safety_check_pass("retinol")
        assert verdict.product_name == "retinol"
        assert verdict.overall_verdict == "caution"
        print("[SUCCESS] Independent turn run completed successfully.")

        # Case 2: Run within an existing active session
        state = AgentSessionState(user_query="retinol")
        async with session_scope(state):
            # Run Pass 1
            verdict1 = await run_safety_check_pass("retinol")
            assert state.pass1_verdict is not None
            assert state.pass1_verdict.product_name == "retinol"
            assert state.pass1_verdict.overall_verdict == "caution"
            assert state.pass2_verdict is None
            print("[SUCCESS] Pass 1 updated active session state correctly.")

            # Prepare Pass 2 response
            dummy_json_pass2 = (
                '{"product_name": "retinol", "overall_verdict": "safe", '
                '"overall_reason": "Sufficient research cited after critique.", "ingredients": []}'
            )
            mock_part.text = dummy_json_pass2

            # Run Pass 2 with critique
            verdict2 = await run_safety_check_pass("retinol", critique="Lookup PubMed databases")
            assert state.critique == "Lookup PubMed databases"
            assert state.pass2_verdict is not None
            assert state.pass2_verdict.overall_verdict == "safe"
            print("[SUCCESS] Pass 2 updated active session state and critique correctly.")

    print("--- Programmatic Runner & State Updates Test Passed ---\n")


async def test_mocked_judge_audit():
    print("--- Running Test: Groundedness Auditor Audit ---")

    dummy_audit_json = (
        '{"is_approved": false, "groundedness_score": 0.60, '
        '"authority_score": 0.50, "tone_safety_score": 0.70, '
        '"critique": "Need higher authority sources."}'
    )

    mock_part = MagicMock()
    mock_part.text = dummy_audit_json
    mock_part.function_call = None
    mock_part.function_response = None

    mock_event = MagicMock()
    mock_event.content.parts = [mock_part]

    async def mock_run_async(*args, **kwargs):
        yield mock_event

    mock_runner = MagicMock()
    mock_runner.session_service.create_session = AsyncMock()
    mock_runner.run_async = mock_run_async

    with mock_runner_context(mock_runner):
        # Create a session state with a Pass 1 verdict
        state = AgentSessionState(user_query="retinol")
        state.pass1_verdict = SafetyVerdict(
            product_name="retinol",
            overall_verdict="caution",
            overall_reason="Testing",
            ingredients=[],
        )

        async with session_scope(state):
            audit = await run_groundedness_audit()
            assert audit.is_approved is False
            assert audit.groundedness_score == 0.60
            assert audit.critique == "Need higher authority sources."
            print("[SUCCESS] Groundedness Auditor completed audit successfully.")

    print("--- Groundedness Auditor Audit Test Passed ---\n")


async def test_mocked_cli_loop():
    print("--- Running Test: Full Multi-Pass CLI Loop ---")

    dummy_pass1_json = (
        '{"product_name": "retinol", "overall_verdict": "caution", '
        '"overall_reason": "Pass 1 summary.", "ingredients": []}'
    )

    dummy_audit_json = (
        '{"is_approved": false, "groundedness_score": 0.75, '
        '"authority_score": 0.65, "tone_safety_score": 0.80, '
        '"critique": "Please search PubMed specifically for retinol toxicity and refine tone."}'
    )

    dummy_pass2_json = (
        '{"product_name": "retinol", "overall_verdict": "safe", '
        '"overall_reason": "Pass 2 summary (fixed).", "ingredients": []}'
    )

    run_async_calls = 0

    # Custom mock runner implementation using call counter
    async def dynamic_run_async(*args, **kwargs):
        nonlocal run_async_calls
        run_async_calls += 1
        mock_part = MagicMock()

        if run_async_calls == 1:
            # Pass 1: Safety Verdict
            mock_part.text = dummy_pass1_json
        elif run_async_calls == 2:
            # Audit Verdict
            mock_part.text = dummy_audit_json
        elif run_async_calls == 3:
            # Pass 2: Refined Safety Verdict
            mock_part.text = dummy_pass2_json
        else:
            mock_part.text = "{}"

        mock_part.function_call = None
        mock_part.function_response = None

        mock_event = MagicMock()
        mock_event.content.parts = [mock_part]
        yield mock_event

    mock_runner = MagicMock()
    mock_runner.session_service.create_session = AsyncMock()
    mock_runner.run_async = dynamic_run_async

    with mock_runner_context(mock_runner):
        from main import run_turn

        await run_turn("retinol")

        # Verify that all three phases of the loop executed correctly
        assert run_async_calls == 3
        print("[SUCCESS] Full multi-pass CLI loop executed with both passes and auditor.")

    print("--- Full Multi-Pass CLI Loop Test Passed ---\n")


async def main():
    await test_session_isolation()
    await test_mocked_run_pass()
    await test_mocked_judge_audit()
    await test_mocked_cli_loop()
    print("All Open-Core offline tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
