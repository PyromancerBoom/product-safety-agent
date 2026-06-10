

"""One ADK turn; tracing via ``instrumentation.setup_tracing``."""

from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from google.adk.runners import InMemoryRunner
from google.genai import types

from instrumentation import setup_tracing
from shopsafe.agent import root_agent
from shopsafe.models import SafetyVerdict


async def run_turn(user_text: str) -> None:
    setup_tracing()
    
    from shopsafe import (
        AgentSessionState,
        session_scope,
        run_safety_check_pass,
        run_groundedness_audit,
    )

    session = AgentSessionState(user_query=user_text)
    
    async with session_scope(session):
        print(f"\n=========================================")
        print(f"[PASS 1] STARTING SAFETY CHECK FOR: '{user_text}'")
        print(f"=========================================")
        try:
            pass1_verdict = await run_safety_check_pass(user_text)
            print("\n--- Pass 1 Verdict Generated ---")
            print(f"Overall Verdict: {pass1_verdict.overall_verdict.upper()}")
            print(f"Reason: {pass1_verdict.overall_reason}")
            for ing in pass1_verdict.ingredients:
                print(f"  - {ing.name}: {ing.verdict.upper()} ({ing.reason})")
        except Exception as e:
            print(f"\n[Pass 1 Error] {e}")
            return

        print(f"\n=========================================")
        print(f"[AUDIT] STARTING GROUNDEDNESS & COMPLIANCE INSPECTOR")
        print(f"=========================================")
        try:
            audit = await run_groundedness_audit()
            print(f"Groundedness Score: {audit.groundedness_score:.2f}/1.00")
            print(f"Authority Score:    {audit.authority_score:.2f}/1.00")
            print(f"Tone Safety Score:  {audit.tone_safety_score:.2f}/1.00")
            print(f"Status:             {'APPROVED' if audit.is_approved else 'REJECTED'}")
        except Exception as e:
            print(f"\n[Audit Error] {e}")
            return

        final_verdict = pass1_verdict

        if not audit.is_approved and audit.critique:
            print(f"\n=========================================")
            print(f"[CRITIQUE] REFINEMENT INSTRUCTIONS RECEIVED")
            print(f"=========================================")
            print(audit.critique)

            print(f"\n=========================================")
            print(f"[PASS 2] STARTING REFINED SEARCH & FIX")
            print(f"=========================================")
            try:
                pass2_verdict = await run_safety_check_pass(user_text, critique=audit.critique)
                print("\n--- Pass 2 (Final) Verdict Generated ---")
                print(f"Overall Verdict: {pass2_verdict.overall_verdict.upper()}")
                print(f"Reason: {pass2_verdict.overall_reason}")
                for ing in pass2_verdict.ingredients:
                    print(f"  - {ing.name}: {ing.verdict.upper()} ({ing.reason})")
                final_verdict = pass2_verdict
            except Exception as e:
                print(f"\n[Pass 2 Error] {e}")
                print("Falling back to Pass 1 verdict.")

        print(f"\n=========================================")
        print(f"[REPORT] FINAL SAFETY REPORT")
        print(f"=========================================")
        print(f"Product:        {final_verdict.product_name}")
        print(f"Overall Rating: {final_verdict.overall_verdict.upper()}")
        print(f"Summary Reason: {final_verdict.overall_reason}")
        print(f"Citations Found: {sum(len(ing.claims) for ing in final_verdict.ingredients)} claim URLs")
        print(f"=========================================")




def main() -> None:
    msg = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What are the safety concerns with retinol in skincare?"
    )
    asyncio.run(run_turn(msg))


if __name__ == "__main__":
    main()
