

import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from dotenv import load_dotenv

from instrumentation import setup_tracing
from shopsafe.prompt import shopsafe_agent_instruction
from shopsafe.tools.search import search

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
)
