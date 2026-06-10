"""Live web search via Exa, exposed as an ADK FunctionTool."""

from __future__ import annotations

import asyncio
import os

from exa_py import Exa
from google.adk.tools import ToolContext


def _format_results(results, snippet_chars: int) -> str:
    blocks = []
    for i, r in enumerate(results, start=1):
        # Prefer highlights (more focused) over raw text truncation
        highlights = getattr(r, "highlights", None) or []
        if highlights:
            snippet = " ... ".join(h.strip() for h in highlights if h)
        else:
            text = (getattr(r, "text", "") or "").strip().replace("\n", " ")
            snippet = text[:snippet_chars] + "..." if len(text) > snippet_chars else text

        blocks.append(
            f"[{i}] {getattr(r, 'title', '') or '(untitled)'}\n"
            f"URL: {getattr(r, 'url', '') or '(no url)'}\n"
            f"Published: {getattr(r, 'published_date', None) or 'unknown'}\n"
            f"Snippet: {snippet or '(no text extracted)'}"
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
      tool_context: ADK tool context (pass None when calling from the pipeline).
      include_domains: Optional list of authoritative domains to restrict results to.
      exclude_domains: Optional list of domains to filter out.
      category: Optional Exa category, e.g. 'research paper' or 'news'.

    Returns:
      Up to N results, each with title, source URL, publish date, and a text snippet.
      Cite the URL for any claim drawn from a result.
    """
    from shopsafe.config import get_config
    from shopsafe.models import normalize_exa_category
    cfg = get_config()

    # Belt-and-suspenders: drop any category Exa would reject (the pipeline
    # already normalizes, but this tool is also callable directly via ADK).
    category = normalize_exa_category(category)

    api_key = (os.environ.get("EXA_API_KEY") or "").strip()
    if not api_key:
        return "Search unavailable: EXA_API_KEY is not set in the environment."

    exa = Exa(api_key=api_key)
    response = await asyncio.to_thread(
        exa.search_and_contents,
        query,
        type="auto",
        num_results=cfg.num_results,
        text=True,
        highlights=True,
        # Pass None rather than [] for unused domain filters (Exa quirk)
        include_domains=include_domains or None,
        exclude_domains=exclude_domains or None,
        category=category,
    )
    results_str = _format_results(getattr(response, "results", []) or [], cfg.snippet_chars)
    from shopsafe.session import log_search
    log_search(query, results_str)
    return results_str
