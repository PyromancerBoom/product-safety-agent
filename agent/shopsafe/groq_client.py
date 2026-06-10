"""Temporary Groq client wrapper to enable high-speed offline/sandbox testing without Gemini rate limits."""

import json
import os
from typing import Optional
import httpx

from shopsafe.models import SafetyVerdict, AuditVerdict

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def call_groq_safety(
    user_text: str, search_results: str, critique: Optional[str] = None
) -> SafetyVerdict:
    """Invokes Groq Llama 3 model to generate SafetyVerdict from search results."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment.")

    from shopsafe.prompt import shopsafe_agent_instruction

    if critique:
        message_content = (
            f"User Query: {user_text}\n\n"
            f"Search Results:\n{search_results}\n\n"
            f"Critique from previous pass:\n{critique}\n\n"
            f"Please perform another search-based safety check to address the critique, "
            f"refine your analysis, and output the final SafetyVerdict JSON."
        )
    else:
        message_content = (
            f"User Query: {user_text}\n\n"
            f"Search Results:\n{search_results}"
        )

    system_prompt = shopsafe_agent_instruction + "\n\n" + """You MUST output a JSON object containing ONLY the following keys:
{
  "product_name": string,
  "overall_verdict": "safe" | "caution" | "avoid",
  "overall_reason": string,
  "ingredients": [
    {
      "name": string,
      "verdict": "safe" | "caution" | "avoid",
      "reason": string,
      "claims": [
        {
          "text": string,
          "url": string
        }
      ]
    }
  ]
}
"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(GROQ_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

    return SafetyVerdict.model_validate_json(content)


async def call_groq_audit(
    user_query: str, search_history_str: str, verdict_json: str
) -> AuditVerdict:
    """Invokes Groq Llama 3 model to perform groundedness audit and produce critique."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment.")

    from shopsafe.prompt import shopsafe_judge_instruction

    prompt = (
        f"User Query:\n{user_query}\n\n"
        f"Search History and Snippets:\n{search_history_str}\n\n"
        f"Safety Verdict under Review:\n{verdict_json}\n"
    )

    system_prompt = shopsafe_judge_instruction + "\n\n" + """You MUST output a JSON object containing ONLY the following keys:
{
  "is_approved": bool,             // true or false
  "groundedness_score": float,     // between 0.0 and 1.0
  "authority_score": float,        // between 0.0 and 1.0
  "tone_safety_score": float,      // between 0.0 and 1.0
  "critique": string               // detailed instructions as a single string, empty if approved
}
Do NOT use any other keys (do NOT create keys like "RATING HONESTY"). The 'critique' key MUST be a string, not an array or list.
"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(GROQ_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

    return AuditVerdict.model_validate_json(content)
