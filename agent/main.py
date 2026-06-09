

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
    app_name, user_id, session_id = "shopsafe", "local_user", secrets.token_hex(8)
    runner = InMemoryRunner(agent=root_agent, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    full_response = ""
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=user_text)]),
        ):
            for part in (event.content.parts if event.content else []) or []:
                if getattr(part, "text", None):
                    text_chunk = part.text
                    full_response += text_chunk
                    print(text_chunk, end="", flush=True)
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    print(f"\n[tool call] {fc.name}({dict(fc.args or {})})", flush=True)
                if getattr(part, "function_response", None):
                    fr = part.function_response
                    resp = str(fr.response)
                    print(f"\n[tool result] {fr.name} -> {resp[:300]}{'...' if len(resp) > 300 else ''}", flush=True)
    except Exception as loop_err:
        print(f"\n[loop error] {loop_err}", flush=True)
    print()
    print("\n--- Schema Validation ---")
    try:
        clean_json = full_response.strip().removeprefix("```json").removesuffix("```").strip()
        verdict = SafetyVerdict.model_validate_json(clean_json)
        print(f"[SUCCESS] Response matches SafetyVerdict schema for product '{verdict.product_name}'")
    except Exception as e:
        print(f"[ERROR] Schema Validation Failed: {e}")




def main() -> None:
    msg = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What are the safety concerns with retinol in skincare?"
    )
    asyncio.run(run_turn(msg))


if __name__ == "__main__":
    main()
