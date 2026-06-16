"""Benchmark evaluation harness for ShopSafe pipeline."""

import argparse
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Windows consoles default to cp1252, which cannot encode the ✅/❌/🎉 status
# glyphs below and crashes the run mid-table. Force UTF-8 on the streams.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Setup python path and dotenv bootstrap from repo root
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "agent"))
sys.path.insert(0, str(repo_root))  # so `evals.cases` resolves when run as a script

load_dotenv(repo_root / ".env")

from instrumentation import setup_tracing
setup_tracing()

from shopsafe.pipeline import run_pipeline, PipelineResult
from shopsafe.config import get_config
from evals.cases import BENCHMARK_CASES, CheckSpec, Case


def evaluate_checks(result: PipelineResult, spec: CheckSpec) -> list[str]:
    """Evaluate declarative checks on the PipelineResult and return a list of failure reasons."""
    errors = []
    v = result.final_verdict

    # 1. context_substring
    if spec.context_substring:
        notes = (v.user_context_notes or "").lower()
        if spec.context_substring.lower() not in notes:
            errors.append(
                f"Context notes '{v.user_context_notes}' did not contain expected substring '{spec.context_substring}'"
            )

    # 2. overall_not
    if spec.overall_not:
        if v.overall_verdict.lower() == spec.overall_not.lower():
            errors.append(
                f"Overall verdict was '{v.overall_verdict}', which is forbidden (overall_not='{spec.overall_not}')"
            )

    # 3. overall_in
    if spec.overall_in:
        allowed = [val.lower() for val in spec.overall_in]
        if v.overall_verdict.lower() not in allowed:
            errors.append(
                f"Overall verdict '{v.overall_verdict}' not in allowed list {spec.overall_in}"
            )

    # 4. min_citations
    if spec.min_citations is not None:
        total_citations = sum(len(ing.claims) for ing in v.ingredients)
        if total_citations < spec.min_citations:
            errors.append(
                f"Total citations {total_citations} < required min {spec.min_citations}"
            )

    # 5. forbid_field (e.g. alternatives)
    if spec.forbid_field:
        if hasattr(v, spec.forbid_field) and getattr(v, spec.forbid_field):
            errors.append(f"Forbidden field '{spec.forbid_field}' was present and non-empty")

    # 6. product_substring
    if spec.product_substring:
        prod = (v.product_name or "").lower()
        if spec.product_substring.lower() not in prod:
            errors.append(
                f"Product name '{v.product_name}' did not contain expected substring '{spec.product_substring}'"
            )

    # 7. claim_substring
    if spec.claim_substring:
        all_claims_text = " ".join(c.text for ing in v.ingredients for c in ing.claims).lower()
        if spec.claim_substring.lower() not in all_claims_text:
            errors.append(
                f"Ingredient claims did not contain expected substring '{spec.claim_substring}'"
            )

    return errors


async def run_case(case: Case) -> tuple[bool, list[str], PipelineResult]:
    """Execute the pipeline for a single case and evaluate checks."""
    try:
        result = await run_pipeline(case.query)
        errors = evaluate_checks(result, case.checks)
        return len(errors) == 0, errors, result
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return False, [f"Pipeline raised exception: {e}\n{tb}"], None


async def run_harness(limit: int | None = None):
    print("=========================================================")
    print("           SHOPSAFE BENCHMARK EVALS HARNESS              ")
    print(f"           Active Config: {get_config().describe()}")
    print("=========================================================\n")

    cases_to_run = BENCHMARK_CASES[:limit] if limit is not None else BENCHMARK_CASES
    total = len(cases_to_run)

    case_results = []
    all_passed = True

    for i, case in enumerate(cases_to_run, start=1):
        print(f"[{i}/{total}] Running Case #{case.id}: '{case.query}'...")
        passed, errors, result = await run_case(case)
        
        if not passed:
            all_passed = False
            print(f"  ❌ FAILED checks:")
            for err in errors:
                print(f"     • {err}")
        else:
            print(f"  ✅ PASSED")

        case_results.append((case, passed, errors, result))
        print("-" * 57)

    # Print summary table of audit scores
    print("\n" + "=" * 80)
    print("                         AUDIT SCORES SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Query Theme (ID)':<25} | {'Ground':<6} | {'Auth':<6} | {'Tone':<6} | {'Mean':<6} | {'Audit Status'}")
    print("-" * 80)

    ground_scores = []
    auth_scores = []
    tone_scores = []
    mean_scores = []

    for case, passed, _, result in case_results:
        theme = case.query[:22] + "..." if len(case.query) > 22 else case.query
        theme_str = f"{theme} (#{case.id})"
        
        if result and result.final_audit:
            audit = result.final_audit
            ground_scores.append(audit.groundedness_score)
            auth_scores.append(audit.authority_score)
            tone_scores.append(audit.tone_safety_score)
            mean_scores.append(audit.mean_score)

            status = "PASSED" if result.approved else "REJECTED"
            print(
                f"{theme_str:<25} | "
                f"{audit.groundedness_score:.2f}  | "
                f"{audit.authority_score:.2f}  | "
                f"{audit.tone_safety_score:.2f}  | "
                f"{audit.mean_score:.2f}  | "
                f"{status}"
            )
        else:
            print(f"{theme_str:<25} | N/A    | N/A    | N/A    | N/A    | N/A (Failed/Mocked)")

    print("-" * 80)
    if mean_scores:
        avg_ground = sum(ground_scores) / len(ground_scores)
        avg_auth = sum(auth_scores) / len(auth_scores)
        avg_tone = sum(tone_scores) / len(tone_scores)
        avg_mean = sum(mean_scores) / len(mean_scores)
        
        min_ground = min(ground_scores)
        min_auth = min(auth_scores)
        min_tone = min(tone_scores)
        min_mean = min(mean_scores)

        print(
            f"{'AVERAGE':<25} | "
            f"{avg_ground:.2f}  | "
            f"{avg_auth:.2f}  | "
            f"{avg_tone:.2f}  | "
            f"{avg_mean:.2f}  | "
            f"-"
        )
        print(
            f"{'MINIMUM':<25} | "
            f"{min_ground:.2f}  | "
            f"{min_auth:.2f}  | "
            f"{min_tone:.2f}  | "
            f"{min_mean:.2f}  | "
            f"-"
        )
    else:
        print("No audit scores available.")
    print("=" * 80)

    # Output final result summary
    passed_count = sum(1 for _, p, _, _ in case_results if p)
    print(f"\nFinal Result: {passed_count}/{total} cases passed.")

    if not all_passed:
        print("❌ Evals failed! Some cases did not satisfy their declarative checks.")
        sys.exit(1)
    else:
        print("🎉 All evals passed successfully!")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="ShopSafe Benchmark Evals Harness")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of benchmark cases to run (useful for cheap smoke runs).",
    )
    args = parser.parse_args()

    asyncio.run(run_harness(limit=args.limit))


if __name__ == "__main__":
    main()
