"""Env-driven pipeline configuration. All model/provider choices live here."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel


Provider = Literal["gemini", "groq"]


class PipelineConfig(BaseModel):
    provider: Provider
    planner_model: str
    verdict_model: str
    judge_model: str
    groq_model: str
    max_refinement_passes: int
    max_planned_queries: int
    num_results: int
    snippet_chars: int
    audit_pass_threshold: float

    def describe(self) -> str:
        """One-line summary of the active provider/models for startup logging."""
        if self.provider == "groq":
            return f"provider=groq model={self.groq_model}"
        return (
            f"provider=gemini planner={self.planner_model} "
            f"verdict={self.verdict_model} judge={self.judge_model}"
        )


@lru_cache(maxsize=1)
def get_config() -> PipelineConfig:
    default_gemini = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    return PipelineConfig(
        provider="groq" if os.environ.get("USE_GROQ") == "1" else "gemini",
        planner_model=os.environ.get("PLANNER_MODEL", default_gemini),
        verdict_model=os.environ.get("VERDICT_MODEL", default_gemini),
        judge_model=os.environ.get("JUDGE_MODEL", default_gemini),
        groq_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        max_refinement_passes=int(os.environ.get("MAX_REFINEMENT_PASSES", "2")),
        max_planned_queries=int(os.environ.get("MAX_PLANNED_QUERIES", "3")),
        num_results=int(os.environ.get("EXA_NUM_RESULTS", "5")),
        snippet_chars=int(os.environ.get("EXA_SNIPPET_CHARS", "800")),
        audit_pass_threshold=float(os.environ.get("AUDIT_PASS_THRESHOLD", "0.85")),
    )
