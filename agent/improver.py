"""ShopSafe Self-Improvement Loop Agent."""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Windows consoles default to cp1252 and crash on the emoji status glyphs below.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Dotenv bootstrap
repo_root = Path(__file__).resolve().parent.parent
load_dotenv(repo_root / ".env")

# Tracing setup
sys.path.insert(0, str(repo_root / "agent"))
from instrumentation import setup_tracing
setup_tracing()

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools import McpToolset
from mcp import StdioServerParameters
from google.genai import types

from shopsafe.config import get_config
from shopsafe.prompt import IMPROVER_INSTRUCTION


async def run_improver():
    print("=========================================================")
    print("           SHOPSAFE SELF-IMPROVEMENT RUNNER             ")
    print("=========================================================\n")

    phoenix_api_key = os.environ.get("PHOENIX_API_KEY", "").strip()
    phoenix_baseUrl = (
        os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "").strip()
        or os.environ.get("PHOENIX_BASE_URL", "").strip()
    )

    if not phoenix_api_key or not phoenix_baseUrl:
        print("❌ Error: Both PHOENIX_API_KEY and PHOENIX_COLLECTOR_ENDPOINT must be set in your environment.")
        sys.exit(1)

    print(f"Connecting to Phoenix MCP server at {phoenix_baseUrl}...")

    # Create the McpToolset for phoenix-mcp
    mcp_toolset = McpToolset(
        connection_params=StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "@arizeai/phoenix-mcp@latest",
                "--apiKey",
                phoenix_api_key,
                "--baseUrl",
                phoenix_baseUrl,
            ],
        )
    )

    cfg = get_config()
    model = cfg.planner_model  # gemini-2.5-flash via config

    print(f"Initializing shopsafe_improver agent with model {model}...")
    # improver uses tools= and NO output_schema (combining them is a bug)
    root_agent = Agent(
        name="shopsafe_improver",
        model=model,
        instruction=IMPROVER_INSTRUCTION,
        tools=[mcp_toolset],
    )

    app_name = "shopsafe"
    user_id = "local_improver_user"
    import secrets
    session_id = secrets.token_hex(8)

    runner = InMemoryRunner(agent=root_agent, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    prompt = (
        "Please query recent ShopSafe traces for the project 'shopsafe', identify any runs "
        "with low audit scores (mean score < 0.85), analyze the failure modes, and write a "
        "concise playbook.md of search-planning rules. Return ONLY the markdown playbook."
    )

    print("Running self-improvement agent (this will invoke the Phoenix MCP server)...")
    full_response = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for part in (event.content.parts if event.content else []) or []:
            if getattr(part, "text", None):
                full_response += part.text

    # Clean the output (strip backticks if LLM fenced it)
    playbook_content = full_response.strip()
    if playbook_content.startswith("```markdown"):
        playbook_content = playbook_content.removeprefix("```markdown").removesuffix("```").strip()
    elif playbook_content.startswith("```"):
        playbook_content = playbook_content.removeprefix("```").removesuffix("```").strip()

    # Save to agent/shopsafe/playbook.md
    playbook_file = Path(__file__).resolve().parent / "shopsafe" / "playbook.md"
    print(f"Writing playbook to {playbook_file}...")
    playbook_file.write_text(playbook_content, encoding="utf-8")
    print("\n🎉 Playbook updated successfully!")
    print("=========================================================")


def main():
    asyncio.run(run_improver())


if __name__ == "__main__":
    main()
