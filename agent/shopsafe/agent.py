

import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from dotenv import load_dotenv

from instrumentation import setup_tracing
from shopsafe.prompt import shopsafe_agent_instruction
from shopsafe.tools.search import search
from shopsafe.models import SafetyVerdict

# Ensure ADK CLI runs (`adk run shopsafe`) load local env and tracing.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
setup_tracing()

_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

root_agent = Agent(
    model=_model,
    name="shopsafe_agent",
    instruction=shopsafe_agent_instruction,
    tools=[
        FunctionTool(func=search),
    ],
    output_schema=SafetyVerdict,
)


async def run_safety_check_pass(user_text: str, critique: str | None = None) -> SafetyVerdict:
    """Runs a single pass of the ShopSafe agent, logging context history to the active session state."""
    from shopsafe.session import get_current_session, session_scope, AgentSessionState
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    import secrets

    session = get_current_session()
    if session is None:
        # Create a new session if none is active
        session = AgentSessionState(user_query=user_text)
        is_new_session = True
    else:
        is_new_session = False

    if critique:
        session.critique = critique

    async def _run():
        app_name = "shopsafe"
        user_id = "local_user"
        session_id = secrets.token_hex(8)

        runner = InMemoryRunner(agent=root_agent, app_name=app_name)
        await runner.session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

        if critique:
            message_content = (
                f"User Query: {user_text}\n\n"
                f"Critique from previous pass:\n{critique}\n\n"
                f"Please perform another search-based safety check to address the critique, "
                f"refine your analysis, and output the final SafetyVerdict JSON."
            )
        else:
            message_content = user_text

        full_response = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message_content)]),
        ):
            for part in (event.content.parts if event.content else []) or []:
                if getattr(part, "text", None):
                    full_response += part.text

        clean_json = full_response.strip().removeprefix("```json").removesuffix("```").strip()
        verdict = SafetyVerdict.model_validate_json(clean_json)

        if critique:
            session.pass2_verdict = verdict
        else:
            session.pass1_verdict = verdict

        return verdict

    if is_new_session:
        async with session_scope(session):
            return await _run()
    else:
        return await _run()

