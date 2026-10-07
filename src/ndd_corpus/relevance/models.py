from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RelevanceLabel = Literal["HIGH", "POSSIBLE", "LOW"]
EvidenceType = Literal[
    "disease_focus",
    "genetic",
    "variant",
    "genotype_phenotype",
    "phenotype",
    "natural_history",
    "onset_progression",
    "patient_case",
]


class RelevanceSignals(BaseModel):
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)


class RetrievalProvenance(BaseModel):
    retrieval_branches: list[str] = Field(default_factory=list)
    mondo_ids: list[str] = Field(default_factory=list)
    matched_search_terms: list[str] = Field(default_factory=list)
    query_ids: list[str] = Field(default_factory=list)


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance_label: RelevanceLabel
    evidence_types: list[EvidenceType] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("evidence_types")
    @classmethod
    def unique_evidence_types(cls, values: list[EvidenceType]) -> list[EvidenceType]:
        return list(dict.fromkeys(values))

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized


class ArticleRelevanceRecord(BaseModel):
    article_id: str
    pmid: str | None
    pmcid: str | None
    relevance_label: RelevanceLabel
    eligible_for_downstream: bool
    evidence_types: list[EvidenceType] = Field(default_factory=list)
    reason: str
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    retrieval_branches: list[str] = Field(default_factory=list)
    mondo_ids: list[str] = Field(default_factory=list)
    matched_search_terms: list[str] = Field(default_factory=list)
    query_ids: list[str] = Field(default_factory=list)
    model_id: str
    prompt_version: str
    prompt_sha256: str = Field(min_length=64, max_length=64)
    request_hash: str = Field(min_length=64, max_length=64)
