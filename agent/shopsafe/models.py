from __future__ import annotations

from typing import List, Literal, Optional, get_args

from pydantic import BaseModel, Field, field_validator

# The only categories Exa accepts. Anything else makes exa_py raise a hard
# ValueError that crashes the pipeline, so this list is the single source of truth.
ExaCategory = Literal[
    "company",
    "research paper",
    "news",
    "pdf",
    "personal site",
    "financial report",
    "people",
]
VALID_EXA_CATEGORIES: frozenset[str] = frozenset(get_args(ExaCategory))


def normalize_exa_category(value: object) -> Optional[str]:
    """Coerce an arbitrary category value to a valid Exa category, or None.

    The planner LLM sometimes invents categories Exa does not support (e.g.
    'guideline', 'regulatory'). Rather than let that crash the search, we drop
    anything off-list to None — the query then runs as a normal web search.
    Matching is case-insensitive so 'News' or 'Research Paper' still resolve.
    """
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned if cleaned in VALID_EXA_CATEGORIES else None


class PlannedQuery(BaseModel):
    query: str = Field(description="The search query string to send to Exa.")
    category: Optional[ExaCategory] = Field(
        default=None,
        description=(
            "Optional Exa result category. MUST be exactly one of: 'company', "
            "'research paper', 'news', 'pdf', 'personal site', 'financial report', "
            "'people'. Omit entirely if none apply — never invent a category."
        ),
    )

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, v: object) -> Optional[str]:
        # Runs before the Literal check, so an off-list value becomes None
        # instead of raising — protects the Groq path, which has no native
        # schema enforcement.
        return normalize_exa_category(v)
    include_domains: Optional[List[str]] = Field(
        default=None,
        description="Optional list of authoritative domains to restrict results to, e.g. ['fda.gov', 'nih.gov'].",
    )
    purpose: str = Field(
        description="One-line explanation of why this query exists — appears in traces."
    )


class ResearchPlan(BaseModel):
    product_name: str = Field(description="Cleaned product name extracted from the user query.")
    ingredients_to_check: List[str] = Field(
        description="List of key ingredients or components to investigate."
    )
    user_context: str = Field(
        description="Any user-specific context extracted (e.g. 'user is 12 years old', 'user is pregnant'). Empty string if none."
    )
    queries: List[PlannedQuery] = Field(
        description="Targeted search queries to run in parallel. Aim for the configured max (default 3)."
    )


class Claim(BaseModel):
    text: str = Field(description="A concise statement of the safety claim or finding.")
    url: str = Field(
        description="The source URL verifying the claim. Must be a valid URL cited from the search results."
    )


class IngredientVerdict(BaseModel):
    name: str = Field(description="Name of the ingredient.")
    verdict: Literal["safe", "caution", "avoid"] = Field(
        description="Safety rating of the ingredient based on evidence."
    )
    reason: str = Field(
        description="A one-line reason summarizing the safety finding. Avoid direct medical diagnostics."
    )
    claims: List[Claim] = Field(
        default_factory=list,
        description="List of specific claims with their source URLs supporting the verdict.",
    )


class SafetyVerdict(BaseModel):
    product_name: str = Field(description="Name of the product or query.")
    overall_verdict: Literal["safe", "caution", "avoid"] = Field(
        description="Overall safety rating of the product/ingredients."
    )
    overall_reason: str = Field(
        description="Concise overall summary. Limit to a few sentences."
    )
    user_context_notes: str = Field(
        description="How this verdict accounts for any user-specific context (age, pregnancy, allergies, etc.). Required — use 'No specific user context provided.' if none."
    )
    ingredients: List[IngredientVerdict] = Field(
        description="Detailed safety analysis per ingredient."
    )


class AuditVerdict(BaseModel):
    is_approved: bool = Field(
        description="True if the safety verdict passes all criteria, False if it needs refinement."
    )
    groundedness_score: float = Field(
        description="Score from 0.0 to 1.0 representing how well the claims are grounded in search results."
    )
    authority_score: float = Field(
        description="Score from 0.0 to 1.0 representing the authority/quality of the cited sources."
    )
    tone_safety_score: float = Field(
        description="Score from 0.0 to 1.0 representing compliance with safety tone framing rules."
    )
    critique: str = Field(
        description="Detailed critique listing weaknesses and specific instructions for refinement. Empty string if approved."
    )

    @property
    def _scores(self) -> tuple[float, float, float]:
        return (self.groundedness_score, self.authority_score, self.tone_safety_score)

    @property
    def mean_score(self) -> float:
        """Average of the three audit dimensions — used to rank verdicts across passes."""
        return sum(self._scores) / 3

    @property
    def min_score(self) -> float:
        """Weakest dimension — the gate, so every dimension must clear the bar."""
        return min(self._scores)

    def meets(self, threshold: float) -> bool:
        """True when all three scores clear `threshold` (the deterministic pass rule)."""
        return self.min_score >= threshold
