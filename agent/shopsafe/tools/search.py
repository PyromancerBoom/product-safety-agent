

"""Live web search via Exa, exposed as an ADK FunctionTool."""

from __future__ import annotations

import asyncio
import os

from exa_py import Exa
from google.adk.tools import ToolContext

_NUM_RESULTS = 3
_SNIPPET_CHARS = 800


def _format_results(results) -> str:
    blocks = []
    for i, r in enumerate(results, start=1):
        text = (getattr(r, "text", "") or "").strip().replace("\n", " ")
        if len(text) > _SNIPPET_CHARS:
            text = text[:_SNIPPET_CHARS] + "..."
        blocks.append(
            f"[{i}] {getattr(r, 'title', '') or '(untitled)'}\n"
            f"URL: {getattr(r, 'url', '') or '(no url)'}\n"
            f"Published: {getattr(r, 'published_date', None) or 'unknown'}\n"
            f"Snippet: {text or '(no text extracted)'}"
        )
    return "\n\n".join(blocks) if blocks else "No results found."


async def search(
    query: str,
    tool_context: ToolContext,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    category: str | None = None,
) -> str:
    """Search the live web for current information.

    Args:
      query: A natural-language search query.
      tool_context: ADK tool context.
      include_domains: Optional list of authoritative domains to search (e.g. ['fda.gov']).
      exclude_domains: Optional list of domains to filter out.
      category: Optional category of results (e.g. 'news', 'research paper').

    Returns:
      Up to five results, each with title, source URL, publish date, and a text
      snippet. Cite the URL for any claim drawn from a result.
    """
    api_key = (os.environ.get("EXA_API_KEY") or "").strip()
    if not api_key:
        return "Search unavailable: EXA_API_KEY is not set in the environment."

    exa = Exa(api_key=api_key)
    response = await asyncio.to_thread(
        exa.search_and_contents,
        query,
        type="auto",
        num_results=_NUM_RESULTS,
        text=True,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        category=category,
    )
    results_str = _format_results(getattr(response, "results", []) or [])
    from shopsafe.session import log_search
    log_search(query, results_str)
    return results_str

