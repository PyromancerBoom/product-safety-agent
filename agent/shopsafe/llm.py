"""Universal structured LLM wrapper — routes to Gemini (ADK) or Groq based on config."""

from __future__ import annotations

import json
import secrets
from typing import TypeVar

import httpx
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from shopsafe.config import get_config

T = TypeVar("T", bound=BaseModel)

_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _schema_hint(schema: type[BaseModel]) -> str:
    """Builds a full JSON Schema hint to append to Groq system prompts.

    Groq's JSON mode guarantees valid JSON but not a particular shape, so we
    hand the model the complete schema (including nested objects and enum
    constraints). Emitting only top-level keys made nested fields like
    `ingredients` look like a string and produced wrong-shaped output.
    """
    return (
        "You MUST output a single JSON object that strictly conforms to the "
        "following JSON Schema. Output ONLY the JSON object — no markdown, no "
        "commentary. Use the property names exactly as defined; do not rename, "
        "add, or omit required fields. For any field constrained to an enum, "
        "use one of the allowed values verbatim.\n\n"
        + json.dumps(schema.model_json_schema(), indent=2)
    )


async def generate_structured(
    *,
    agent_name: str,
    instruction: str,
    user_content: str,
    schema: type[T],
    model: str | None = None,
) -> T:
    """Run one LLM turn and return a validated Pydantic model.

    Uses Gemini via ADK (with output_schema) or Groq (with JSON mode),
    depending on get_config().provider.
    """
    cfg = get_config()

    if cfg.provider == "groq":
        return await _groq(
            instruction=instruction,
            user_content=user_content,
            schema=schema,
            model=cfg.groq_model,  # always use groq_model — never forward a Gemini model name
        )

    return await _gemini(
        agent_name=agent_name,
        instruction=instruction,
        user_content=user_content,
        schema=schema,
        model=model or cfg.verdict_model,
    )


async def _gemini(
    *,
    agent_name: str,
    instruction: str,
    user_content: str,
    schema: type[T],
    model: str,
) -> T:
    agent = Agent(
        model=model,
        name=agent_name,
        instruction=instruction,
        output_schema=schema,
    )

    app_name = "shopsafe"
    user_id = "local_user"
    session_id = secrets.token_hex(8)

    runner = InMemoryRunner(agent=agent, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    full_response = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=user_content)]),
    ):
        for part in (event.content.parts if event.content else []) or []:
            if getattr(part, "text", None):
                full_response += part.text

    clean = full_response.strip().removeprefix("```json").removesuffix("```").strip()
    return schema.model_validate_json(clean)


async def _groq(
    *,
    instruction: str,
    user_content: str,
    schema: type[T],
    model: str,
) -> T:
    import os

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment.")

    system_prompt = instruction + "\n\n" + _schema_hint(schema)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(_GROQ_API_URL, json=payload, headers=headers)
        if not response.is_success:
            raise RuntimeError(
                f"Groq API error {response.status_code} for model '{model}'.\n"
                f"Response body: {response.text}\n"
                f"Tip: check that the model name is valid at console.groq.com, "
                f"or unset USE_GROQ in .env to use Gemini instead."
            )
        content = response.json()["choices"][0]["message"]["content"]

    return schema.model_validate_json(content)
