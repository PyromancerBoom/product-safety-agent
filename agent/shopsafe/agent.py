"""ADK root_agent for `adk run shopsafe` interactive dev mode."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from instrumentation import setup_tracing
from shopsafe.prompt import shopsafe_agent_instruction
from shopsafe.tools.search import search

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
setup_tracing()

_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# No output_schema here — combining tools + output_schema disables tool-calling in ADK.
root_agent = Agent(
    model=_model,
    name="shopsafe_agent",
    instruction=shopsafe_agent_instruction,
    tools=[FunctionTool(func=search)],
)
