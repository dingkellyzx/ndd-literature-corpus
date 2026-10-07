from __future__ import annotations

from ndd_corpus.relevance.models import (
    ArticleRelevanceRecord,
    ClassificationResult,
    RetrievalProvenance,
)
from ndd_corpus.relevance.signals import detect_relevance_signals


def test_detects_terms_from_every_positive_signal_group() -> None:
    signals = detect_relevance_signals(
        "De novo variant natural history",
        "A family cohort had developmental delay and progressive seizure onset.",
    )

    assert "genetic:de novo" in signals.positive_signals
    assert "genetic:variant" in signals.positive_signals
    assert "phenotype:developmental delay" in signals.positive_signals
    assert "phenotype:seizure" in signals.positive_signals
    assert "patient:family" in signals.positive_signals
    assert "patient:cohort" in signals.positive_signals
    assert "temporal:natural history" in signals.positive_signals
    assert "temporal:onset" in signals.positive_signals
    assert "temporal:progressive" in signals.positive_signals


def test_detects_every_negative_focus_signal_case_insensitively() -> None:
    text = " | ".join(
        [
            "SERVICE UTILIZATION",
            "treatment access",
            "health policy",
            "outreach",
            "medication safety",
            "adverse effect",
            "drug toxicity",
            "screening program",
            "behavioral intervention",
            "substance abuse treatment",
        ]
    )

    signals = detect_relevance_signals("", text)

    assert signals.negative_signals == [
        "service utilization",
        "treatment access",
        "health policy",
        "outreach",
        "medication safety",
        "adverse effect",
        "drug toxicity",
        "screening program",
        "behavioral intervention",
        "substance abuse treatment",
    ]


def test_signal_matching_accepts_flexible_whitespace_but_not_word_fragments() -> None:
    signals = detect_relevance_signals(
        "Compound\nheterozygous cases",
        "Whole exome sequencing was used; toxicity alone is not drug toxicity.",
    )

    assert "genetic:compound heterozygous" in signals.positive_signals
    assert "genetic:exome" in signals.positive_signals
    assert "genetic:sequencing" in signals.positive_signals
    assert "genetic:gene" not in signals.positive_signals
    assert signals.negative_signals == ["drug toxicity"]


def test_empty_metadata_has_no_deterministic_signals() -> None:
    signals = detect_relevance_signals("", "")

    assert signals.positive_signals == []
    assert signals.negative_signals == []


def test_relevance_models_use_fixed_vocabularies_and_article_join_key() -> None:
    result = ClassificationResult(
        relevance_label="HIGH",
        evidence_types=["disease_focus", "phenotype"],
        reason="Characterizes an NDD phenotype cohort.",
    )
    provenance = RetrievalProvenance(
        retrieval_branches=["generic_ndd"],
        mondo_ids=["MONDO:0000001"],
        matched_search_terms=["rare syndrome"],
        query_ids=["query-1"],
    )

    record = ArticleRelevanceRecord(
        article_id="PMID:1",
        pmid="1",
        pmcid=None,
        relevance_label=result.relevance_label,
        eligible_for_downstream=True,
        evidence_types=result.evidence_types,
        reason=result.reason,
        positive_signals=["phenotype:phenotype"],
        negative_signals=[],
        **provenance.model_dump(),
        model_id="qwen3:14b",
        prompt_version="1",
        prompt_sha256="a" * 64,
        request_hash="b" * 64,
    )

    assert record.article_id == "PMID:1"
    assert record.evidence_types == ["disease_focus", "phenotype"]
