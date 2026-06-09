"""Thread-safe context session manager for tracking query-level execution state."""

from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import List, Optional
from pydantic import BaseModel, Field

from shopsafe.models import SafetyVerdict


class SearchRecord(BaseModel):
    """Represents a single search query and its formatted results."""
    query: str
    results: str


class AgentSessionState(BaseModel):
    """Sandbox for tracking safety check run history and multi-pass artifacts."""
    user_query: str
    pass1_verdict: Optional[SafetyVerdict] = None
    critique: Optional[str] = None
    pass2_verdict: Optional[SafetyVerdict] = None
    search_history: List[SearchRecord] = Field(default_factory=list)


# ContextVar to hold the active session state
session_state_var: ContextVar[Optional[AgentSessionState]] = ContextVar(
    "session_state", default=None
)


def get_current_session() -> Optional[AgentSessionState]:
    """Retrieves the active AgentSessionState from the context variables."""
    return session_state_var.get()


def log_search(query: str, results: str) -> None:
    """Appends a search record to the active session state, if one exists."""
    session = get_current_session()
    if session is not None:
        session.search_history.append(SearchRecord(query=query, results=results))


@asynccontextmanager
async def session_scope(state: AgentSessionState):
    """Async context manager to safely set and restore the session state ContextVar."""
    token = session_state_var.set(state)
    try:
        yield state
    finally:
        session_state_var.reset(token)
