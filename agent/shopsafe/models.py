from pydantic import BaseModel, Field
from typing import List, Literal


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
        default=[],
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
    ingredients: List[IngredientVerdict] = Field(
        description="Detailed safety analysis per ingredient."
    )
    alternatives: List[AlternativeRecommendation] = Field(
        default_factory=list,
        description="Safe, clean alternatives suggested if the overall verdict is caution or avoid.",
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
        description="Detailed critique listing weaknesses and specific instructions for refinement. Empty if approved."
    )
