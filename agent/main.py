"""One-shot ShopSafe pipeline run with Phoenix tracing."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from instrumentation import setup_tracing  # noqa: E402

setup_tracing()

from shopsafe.pipeline import run_pipeline  # noqa: E402


def _banner(msg: str) -> None:
    print(f"\n{'=' * 45}")
    print(f"  {msg}")
    print(f"{'=' * 45}")


async def run_turn(user_text: str) -> None:
    from shopsafe.config import get_config

    _banner(f"CONFIG  {get_config().describe()}")
    result = await run_pipeline(user_text, on_stage=_banner)

    # ── Plan summary ──────────────────────────────────────────
    for i, plan in enumerate(result.plans, start=1):
        _banner(f"PASS {i} PLAN")
        print(f"Product:     {plan.product_name}")
        if plan.user_context:
            print(f"User ctx:    {plan.user_context}")
        print(f"Ingredients: {', '.join(plan.ingredients_to_check)}")
        print(f"Queries ({len(plan.queries)}):")
        for pq in plan.queries:
            domains = f" [{', '.join(pq.include_domains)}]" if pq.include_domains else ""
            print(f"  • {pq.query}{domains}")
            print(f"    ↳ {pq.purpose}")

    # ── Audit scores per pass ─────────────────────────────────
    for i, audit in enumerate(result.audits, start=1):
        _banner(f"PASS {i} AUDIT")
        print(f"Groundedness:  {audit.groundedness_score:.2f}/1.00")
        print(f"Authority:     {audit.authority_score:.2f}/1.00")
        print(f"Tone Safety:   {audit.tone_safety_score:.2f}/1.00")
        status = "APPROVED" if audit.is_approved else "REJECTED"
        print(f"Status:        {status}")
        if audit.critique:
            print(f"\nCritique:\n{audit.critique}")

    # ── Final report ──────────────────────────────────────────
    v = result.final_verdict
    _banner("FINAL SAFETY REPORT")
    print(f"Product:        {v.product_name}")
    print(f"Overall Rating: {v.overall_verdict.upper()}")
    print(f"Summary:        {v.overall_reason}")
    if v.user_context_notes:
        print(f"User Context:   {v.user_context_notes}")
    print(f"Passes used:    {result.passes_used}")
    a = result.final_audit
    if a is not None:
        if result.approved:
            print(f"Audit:          PASSED (mean {a.mean_score:.2f})")
        else:
            print(
                f"Audit:          NOT PASSED — best-effort verdict "
                f"(mean {a.mean_score:.2f}, weakest {a.min_score:.2f}). Treat with extra caution."
            )
    print()
    for ing in v.ingredients:
        print(f"  [{ing.verdict.upper()}] {ing.name}")
        print(f"         {ing.reason}")
        for claim in ing.claims:
            print(f"         • {claim.text}")
            print(f"           {claim.url}")
    total_claims = sum(len(ing.claims) for ing in v.ingredients)
    print(f"\nCitations found: {total_claims}")
    print("=" * 45)
    print("\n>>> Check the Phoenix UI for the full trace tree.")


def main() -> None:
    msg = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What are the safety concerns with retinol in skincare?"
    )
    asyncio.run(run_turn(msg))


if __name__ == "__main__":
    main()
