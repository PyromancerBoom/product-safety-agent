"""Groundedness and safety auditor — evaluates a SafetyVerdict against search evidence."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from shopsafe.config import get_config
from shopsafe.llm import generate_structured
from shopsafe.models import AuditVerdict
from shopsafe.prompt import shopsafe_judge_instruction
from shopsafe.session import get_current_session

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


async def run_groundedness_audit() -> AuditVerdict:
    """Audits the most recent SafetyVerdict in the active session against search history."""
    session = get_current_session()
    if session is None:
        raise ValueError("No active session found. Audits must run within a session context.")

    verdict = session.pass2_verdict or session.pass1_verdict
    if verdict is None:
        raise ValueError("No safety verdict found in the active session to audit.")

    search_blocks = []
    for idx, record in enumerate(session.search_history, start=1):
        search_blocks.append(
            f"Search #{idx}\nQuery: {record.query}\nResults Snippets:\n{record.results}\n"
        )
    search_history_str = "\n".join(search_blocks) if search_blocks else "No search history found."

    prompt = (
        f"User Query:\n{session.user_query}\n\n"
        f"Search History and Snippets:\n{search_history_str}\n\n"
        f"Safety Verdict under Review:\n{verdict.model_dump_json(indent=2)}\n"
    )

    return await generate_structured(
        agent_name="shopsafe_judge",
        instruction=shopsafe_judge_instruction,
        user_content=prompt,
        schema=AuditVerdict,
        model=get_config().judge_model,
    )
