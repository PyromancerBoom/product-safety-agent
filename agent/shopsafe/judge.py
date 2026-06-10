"""Groundedness and safety auditor agent that evaluates the safety verdict against search results."""

import os
from pathlib import Path
from dotenv import load_dotenv

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
import secrets

from shopsafe.prompt import shopsafe_judge_instruction
from shopsafe.models import AuditVerdict
from shopsafe.session import get_current_session

# Load env for running judge standalone or in tests
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Define the auditor agent
judge_agent = Agent(
    model=_model,
    name="shopsafe_judge_agent",
    instruction=shopsafe_judge_instruction,
    output_schema=AuditVerdict,
)


async def run_groundedness_audit() -> AuditVerdict:
    """Audits the Pass 1 SafetyVerdict of the current active session against its search snippets."""
    session = get_current_session()
    if session is None:
        raise ValueError("No active session found. Audits must run within a session context.")

    if session.pass1_verdict is None:
        raise ValueError("No Pass 1 safety verdict found in the active session to audit.")

    # Serialize search snippets
    search_blocks = []
    for idx, record in enumerate(session.search_history, start=1):
        search_blocks.append(
            f"Search #{idx}\nQuery: {record.query}\nResults Snippets:\n{record.results}\n"
        )
    search_history_str = "\n".join(search_blocks) if search_blocks else "No search history found."

    # Serialize verdict
    verdict_json = session.pass1_verdict.model_dump_json(indent=2)

    if os.environ.get("USE_GROQ") == "1":
        from shopsafe.groq_client import call_groq_audit
        print("\n[Using GROQ with mode llama-3.3-70b-versatile]")
        audit_result = await call_groq_audit(session.user_query, search_history_str, verdict_json)
        return audit_result

    # Format prompt for the judge
    prompt = (
        f"User Query:\n{session.user_query}\n\n"
        f"Search History and Snippets:\n{search_history_str}\n\n"
        f"Safety Verdict under Review:\n{verdict_json}\n"
    )

    app_name = "shopsafe"
    user_id = "local_user"
    session_id = secrets.token_hex(8)

    runner = InMemoryRunner(agent=judge_agent, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    full_response = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for part in (event.content.parts if event.content else []) or []:
            if getattr(part, "text", None):
                full_response += part.text

    clean_json = full_response.strip().removeprefix("```json").removesuffix("```").strip()
    audit_result = AuditVerdict.model_validate_json(clean_json)

    return audit_result
