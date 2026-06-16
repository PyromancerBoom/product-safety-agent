"""Declarative evaluation cases for the ShopSafe pipeline."""

from typing import List, Optional
from pydantic import BaseModel, Field


class CheckSpec(BaseModel):
    context_substring: Optional[str] = Field(
        None, description="String that must appear in final_verdict.user_context_notes."
    )
    overall_not: Optional[str] = Field(
        None, description="Verdict that must NOT be returned (e.g. 'safe')."
    )
    overall_in: Optional[List[str]] = Field(
        None, description="Allowed overall verdicts (e.g. ['caution', 'avoid'])."
    )
    min_citations: Optional[int] = Field(
        None, description="Minimum number of total cited claims across all ingredients."
    )
    forbid_field: Optional[str] = Field(
        None, description="Field name that must not be set or present in SafetyVerdict."
    )
    product_substring: Optional[str] = Field(
        None, description="String that must appear in final_verdict.product_name."
    )
    claim_substring: Optional[str] = Field(
        None,
        description="String that must appear in at least one ingredient claim text.",
    )


class Case(BaseModel):
    id: int
    query: str
    checks: CheckSpec


BENCHMARK_CASES = [
    Case(
        id=1,
        query="Planning to buy ON whey protein gold standard as a 12 year old",
        checks=CheckSpec(
            context_substring="12",
            overall_not="safe",
            product_substring="whey",
        ),
    ),
    Case(
        id=2,
        query="retinol serum, 8 weeks pregnant",
        checks=CheckSpec(
            context_substring="pregnant",
            overall_in=["caution", "avoid"],
            product_substring="retinol",
        ),
    ),
    Case(
        id=3,
        query="Hydroxycut hardcore buying in bulk",
        checks=CheckSpec(
            claim_substring="recall",
            overall_in=["caution", "avoid"],
            product_substring="Hydroxycut",
        ),
    ),
    Case(
        id=4,
        query="Senomyx flavor enhancer chips",
        checks=CheckSpec(
            overall_in=["caution", "avoid"],
            product_substring="Senomyx",
        ),
    ),
    Case(
        id=5,
        query="organic extra virgin olive oil for cooking",
        checks=CheckSpec(
            overall_in=["safe"],
            min_citations=1,
            product_substring="olive oil",
        ),
    ),
    Case(
        id=6,
        query="protien powdr for gym hevy liftng",
        checks=CheckSpec(
            product_substring="protein",
        ),
    ),
    Case(
        id=7,
        query="peanut butter powder, severe tree nut allergy",
        checks=CheckSpec(
            context_substring="allergy",
            overall_not="safe",
            product_substring="peanut",
        ),
    ),
    Case(
        id=8,
        query="spray sunscreen benzene recall valisure",
        checks=CheckSpec(
            overall_in=["caution", "avoid"],
            min_citations=1,
            product_substring="sunscreen",
        ),
    ),
    Case(
        id=9,
        query="diet coke aspartame safe",
        checks=CheckSpec(
            overall_in=["caution"],
            min_citations=1,
            product_substring="diet coke",
        ),
    ),
    Case(
        id=10,
        query="buying both melatonin gummies and zzzquil",
        checks=CheckSpec(
            product_substring="melatonin",
        ),
    ),
]
