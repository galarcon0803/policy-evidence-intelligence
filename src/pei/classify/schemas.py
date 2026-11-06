"""Structured classifier output, and a deterministic check that its evidence is real."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PILLARS = (
    "electricity_affordability",
    "data_centers_communities",
    "education_learning",
    "jobs_skills",
)
RELEVANT_AT = 2
Pillar = Literal[
    "electricity_affordability",
    "data_centers_communities",
    "education_learning",
    "jobs_skills",
]
SourceField = Literal["title", "policy_area", "crs_summary", "latest_action", "bill_text"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Strict):
    source_field: SourceField
    quote: str


class PillarAssessment(Strict):
    pillar: Pillar
    relevance: int
    rationale: str
    evidence: list[Evidence]

    @model_validator(mode="after")
    def _check(self):
        if not 0 <= self.relevance <= 3:
            raise ValueError("relevance must be between 0 and 3")
        if self.relevance > 0 and not self.evidence:
            raise ValueError(f"{self.pillar} scored {self.relevance} with no evidence")
        return self


class Lens(Strict):
    applies: bool
    rationale: str
    evidence: list[Evidence]

    @model_validator(mode="after")
    def _check(self):
        if self.applies and not self.evidence:
            raise ValueError("a lens that applies needs evidence")
        return self


class PolicyQuestion(Strict):
    question: str
    evidence: list[Evidence] = Field(min_length=1)


class Classification(Strict):
    pillars: list[PillarAssessment]
    safety: Lens
    equity: Lens
    governance: Lens
    questions: list[PolicyQuestion]

    @model_validator(mode="after")
    def _check(self):
        names = sorted(item.pillar for item in self.pillars)
        if names != sorted(PILLARS):
            raise ValueError(f"expected each pillar exactly once, got {names}")
        relevant = any(item.relevance >= RELEVANT_AT for item in self.pillars)
        if relevant and not 2 <= len(self.questions) <= 4:
            raise ValueError("a relevant bill needs 2 to 4 questions")
        if not relevant and self.questions:
            raise ValueError("a bill with no relevant pillar must have no questions")
        return self


def output_schema() -> dict:
    """JSON schema for the API, omitting keywords that structured output does not support."""

    def clean(node):
        if isinstance(node, dict):
            node = {
                k: clean(v) for k, v in node.items() if k not in ("title", "minItems", "default")
            }
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = sorted(node.get("properties", {}))
            return node
        if isinstance(node, list):
            return [clean(item) for item in node]
        return node

    return clean(deepcopy(Classification.model_json_schema()))


def _normalize(text: str) -> str:
    """Compare ignoring case, whitespace, and typographic variants, not wording."""
    replaced = text.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}))
    return re.sub(r"\s+", " ", replaced).strip().lower()


def iter_evidence(result: Classification):
    for item in result.pillars:
        for evidence in item.evidence:
            yield f"pillar:{item.pillar}", evidence
    for name in ("safety", "equity", "governance"):
        for evidence in getattr(result, name).evidence:
            yield f"lens:{name}", evidence
    for index, question in enumerate(result.questions):
        for evidence in question.evidence:
            yield f"question:{index}", evidence


def verify_quotes(result: Classification, document: dict[str, str | None]) -> list[dict]:
    """Return each cited quote that does not appear in the source field it names."""
    failures = []
    for where, evidence in iter_evidence(result):
        field = _normalize(document.get(evidence.source_field) or "")
        if not evidence.quote.strip() or _normalize(evidence.quote) not in field:
            failures.append(
                {"where": where, "source_field": evidence.source_field, "quote": evidence.quote}
            )
    return failures


def count_quotes(result: Classification) -> int:
    return sum(1 for _ in iter_evidence(result))
