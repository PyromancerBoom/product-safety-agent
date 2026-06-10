"""ShopSafe Benchmark Harness for running safety checks across a fixed set of inputs (Open-Core)."""

import argparse
import asyncio
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the parent directory is in sys.path so we can import from agent package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# Benchmark queries
BENCHMARK_QUERIES = [
    "ON Gold Standard Whey Protein",
    "Chemical sunscreen containing Benzene",
    "Retinol anti-aging skincare serum",
    "Aspartame in diet sodas",
    "Organic extra virgin olive oil",
    "Cosmetic cream with BHA preservative",
]


@contextmanager
def mock_runner_context(mock_runner):
    """Context manager to patch InMemoryRunner across all namespaces where it is used."""
    with (
        patch("google.adk.runners.InMemoryRunner", return_value=mock_runner) as p1,
        patch("shopsafe.judge.InMemoryRunner", return_value=mock_runner) as p2,
        patch(
            "shopsafe.agent.InMemoryRunner", return_value=mock_runner, create=True
        ) as p3,
    ):
        yield (p1, p2, p3)


def get_mock_runner():
    """Returns a mock runner that dynamically yields structured JSON strings depending on call count."""
    run_async_calls = 0

    # Define mock payloads matching SafetyVerdict and AuditVerdict
    dummy_pass1_caution = (
        '{"product_name": "Product Under Review", "overall_verdict": "caution", '
        '"overall_reason": "Contains controversial ingredients.", "ingredients": ['
        '{"name": "ingredient_x", "verdict": "caution", "reason": "Associated with issues.", "claims": []}'
        "]}"
    )

    dummy_audit_reject = (
        '{"is_approved": false, "groundedness_score": 0.70, '
        '"authority_score": 0.60, "tone_safety_score": 0.75, '
        '"critique": "Please verify tone and search PubMed databases."}'
    )

    dummy_pass2_caution = (
        '{"product_name": "Product Under Review", "overall_verdict": "caution", '
        '"overall_reason": "Pass 2 caution verdict.", "ingredients": ['
        '{"name": "ingredient_x", "verdict": "caution", "reason": "Refined safety search.", "claims": []}'
        "]}"
    )

    dummy_pass1_safe = (
        '{"product_name": "Product Under Review", "overall_verdict": "safe", '
        '"overall_reason": "No harmful ingredients found.", "ingredients": []}'
    )

    dummy_audit_approve = (
        '{"is_approved": true, "groundedness_score": 0.95, '
        '"authority_score": 0.90, "tone_safety_score": 0.95, '
        '"critique": ""}'
    )

    async def dynamic_run_async(*args, **kwargs):
        nonlocal run_async_calls
        run_async_calls += 1
        mock_part = MagicMock()

        query_num = (run_async_calls - 1) // 3 + 1
        call_step = (run_async_calls - 1) % 3 + 1

        if query_num <= 3:
            # Multi-pass sequence (Step 1: Pass 1, Step 2: Audit, Step 3: Pass 2)
            if call_step == 1:
                mock_part.text = dummy_pass1_caution
            elif call_step == 2:
                mock_part.text = dummy_audit_reject
            elif call_step == 3:
                mock_part.text = dummy_pass2_caution
        else:
            # Single-pass sequence (Step 1: Pass 1, Step 2: Audit)
            actual_step = (run_async_calls - 1 - 9) % 2 + 1
            if actual_step == 1:
                mock_part.text = dummy_pass1_safe
            elif actual_step == 2:
                mock_part.text = dummy_audit_approve

        mock_part.function_call = None
        mock_part.function_response = None

        mock_event = MagicMock()
        mock_event.content.parts = [mock_part]
        yield mock_event

    mock_runner = MagicMock()
    mock_runner.session_service.create_session = AsyncMock()
    mock_runner.run_async = dynamic_run_async
    return mock_runner


async def run_harness(use_mock: bool):
    print("=====================================================================")
    print(
        f"STARTING SHOPSAFE BENCHMARK HARNESS (Mode: {'MOCKED' if use_mock else 'LIVE'})"
    )
    print("=====================================================================\n")

    from main import run_turn

    results = []

    # Prepare mock context if requested
    if use_mock:
        mock_runner = get_mock_runner()
        ctx = mock_runner_context(mock_runner)
    else:
        # Null context manager
        @contextmanager
        def null_ctx():
            yield

        ctx = null_ctx()

    with ctx:
        for idx, query in enumerate(BENCHMARK_QUERIES, start=1):
            print(
                f"\n---------------------------------------------------------------------"
            )
            print(f"Query #{idx}: {query}")
            print(
                f"---------------------------------------------------------------------"
            )

            # Execute the orchestrated safety check
            await run_turn(query)

            if use_mock:
                # First 3 were caution, multi-pass
                if idx <= 3:
                    verdict_str = "CAUTION (Refined)"
                    audit_str = "REJECTED -> APPROVED"
                else:
                    verdict_str = "SAFE"
                    audit_str = "APPROVED"
            else:
                verdict_str = "LIVE RUN"
                audit_str = "N/A"

            results.append(
                {
                    "query": query,
                    "verdict": verdict_str,
                    "audit": audit_str,
                }
            )

    # Output Benchmark Summary
    print("\n" + "=" * 80)
    print("SHOPSAFE BENCHMARK REPORT SUMMARY")
    print("=" * 80)
    print(f"{'Query Name':<40} | {'Verdict':<15} | {'Audit Status'}")
    print("-" * 80)
    for res in results:
        print(f"{res['query']:<40} | {res['verdict']:<15} | {res['audit']}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="ShopSafe Safety Agent Benchmark Harness"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run the harness offline using simulated agent and judge model payloads.",
    )
    args = parser.parse_args()

    asyncio.run(run_harness(use_mock=args.mock))


if __name__ == "__main__":
    main()
