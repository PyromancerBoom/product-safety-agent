

from pydantic import BaseModel, Field
from typing import List, Literal

class Claim(BaseModel):
    text: str = Field(description="A concise statement of the safety claim or finding.")
    url: str = Field(description="The source URL verifying the claim. Must be a valid URL cited from the search results.")

class IngredientVerdict(BaseModel):
    name: str = Field(description="Name of the ingredient.")
    verdict: Literal["safe", "caution", "avoid"] = Field(description="Safety rating of the ingredient based on evidence.")
    reason: str = Field(description="A one-line reason summarizing the safety finding. Avoid direct medical diagnostics.")
    claims: List[Claim] = Field(default=[], description="List of specific claims with their source URLs supporting the verdict.")

class SafetyVerdict(BaseModel):
    product_name: str = Field(description="Name of the product or query.")
    overall_verdict: Literal["safe", "caution", "avoid"] = Field(description="Overall safety rating of the product/ingredients.")
    overall_reason: str = Field(description="Concise overall summary. Limit to a few sentences.")
    ingredients: List[IngredientVerdict] = Field(description="Detailed safety analysis per ingredient.")
