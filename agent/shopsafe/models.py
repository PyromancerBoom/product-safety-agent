from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PlannedQuery(BaseModel):
    query: str = Field(description="The search query string to send to Exa.")
    category: Optional[str] = Field(
        default=None,
        description="Optional Exa result category, e.g. 'research paper' or 'news'.",
    )
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
