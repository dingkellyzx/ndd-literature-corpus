from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ndd_corpus.config import RelevanceConfig
from ndd_corpus.relevance.classifier import RelevanceClassifierError
from ndd_corpus.relevance.models import (
    ClassificationResult,
    RelevanceSignals,
    RetrievalProvenance,
)
from ndd_corpus.relevance.screen import (
    RELEVANCE_SCHEMA,
    aggregate_retrieval_provenance,
    build_debug_report,
    screen_articles,
    summarize_relevance_records,
    write_screen_outputs,
)


class CountingClassifier:
    def __init__(self, results: list[ClassificationResult]) -> None:
        self.results = results
        self.calls: list[tuple[dict[str, object], RetrievalProvenance, RelevanceSignals]] = []

    def classify(
        self,
        article: dict[str, object],
        provenance: RetrievalProvenance,
        signals: RelevanceSignals,
    ) -> ClassificationResult:
        self.calls.append((dict(article), provenance, signals))
        return self.results[len(self.calls) - 1]


class FailingClassifier:
    def __init__(self) -> None:
        self.calls = 0

    def classify(
        self,
        article: dict[str, object],
        provenance: RetrievalProvenance,
        signals: RelevanceSignals,
    ) -> ClassificationResult:
        self.calls += 1
        raise RelevanceClassifierError("Ollama timed out")


def _article(
    article_id: str,
    pmid: str | None,
    *,
    title: str = "Rare neurodevelopmental syndrome",
    abstract: str | None = "A patient cohort had developmental delay.",
) -> dict[str, object]:
    return {
        "article_id": article_id,
        "pmid": pmid,
        "pmcid": None,
        "title": title,
        "abstract": abstract,
        "publication_types": ["Journal Article"],
        "mesh_terms": ["Neurodevelopmental Disorders"],
        "keywords": [],
    }


def _result(label: str) -> ClassificationResult:
    evidence = ["disease_focus", "patient_case"] if label != "LOW" else []
    return ClassificationResult(
        relevance_label=label,  # type: ignore[arg-type]
        evidence_types=evidence,  # type: ignore[arg-type]
        reason=f"Classified as {label} from supplied metadata.",
    )


def test_aggregate_provenance_keeps_all_unique_values_deterministically() -> None:
    rows = [
        {
            "pmid": "7",
            "mondo_id": "MONDO:2",
            "retrieval_branch": "broad_ndd",
            "matched_search_term": None,
            "query_id": "q2",
        },
        {
            "pmid": "7",
            "mondo_id": "MONDO:1",
            "retrieval_branch": "disease",
            "matched_search_term": "Rare syndrome",
            "query_id": "q1",
        },
        {
            "pmid": "7",
            "mondo_id": "MONDO:1",
            "retrieval_branch": "disease",
            "matched_search_term": "Rare syndrome",
            "query_id": "q1",
        },
    ]

    provenance = aggregate_retrieval_provenance(rows)["7"]

    assert provenance.retrieval_branches == ["broad_ndd", "disease"]
    assert provenance.mondo_ids == ["MONDO:1", "MONDO:2"]
    assert provenance.matched_search_terms == ["Rare syndrome"]
    assert provenance.query_ids == ["q1", "q2"]


def test_screening_writes_one_record_per_article_and_filters_sections(tmp_path: Path) -> None:
    articles = [_article("PMID:1", "1"), _article("PMID:2", "2")]
    sections = [
        {"article_id": "PMID:1", "text": "keep"},
        {"article_id": "PMID:2", "text": "remove"},
    ]
    classifier = CountingClassifier([_result("HIGH"), _result("LOW")])

    screened = screen_articles(
        articles,
        [],
        sections,
        config=RelevanceConfig(max_retries=0),
        cache_dir=tmp_path / "cache",
        error_audit_path=tmp_path / "errors.jsonl",
        classifier=classifier,
    )

    assert [record.article_id for record in screened.records] == ["PMID:1", "PMID:2"]
    assert [record.eligible_for_downstream for record in screened.records] == [True, False]
    assert [row["article_id"] for row in screened.articles_relevant] == ["PMID:1"]
    assert [row["text"] for row in screened.sections_relevant] == ["keep"]


def test_keep_labels_controls_ordinary_classification_eligibility(tmp_path: Path) -> None:
    classifier = CountingClassifier([_result("LOW")])

    screened = screen_articles(
        [_article("PMID:1", "1")],
        [],
        [],
        config=RelevanceConfig(keep_labels=["LOW"]),
        cache_dir=tmp_path / "cache",
        error_audit_path=tmp_path / "errors.jsonl",
        classifier=classifier,
    )

    assert screened.records[0].eligible_for_downstream is True
    assert [row["article_id"] for row in screened.articles_relevant] == ["PMID:1"]


def test_disabled_screening_retains_every_article_without_calling_classifier(
    tmp_path: Path,
) -> None:
    classifier = CountingClassifier([_result("LOW")])
    articles = [_article("PMID:1", "1"), _article("PMID:2", "2")]

    screened = screen_articles(
        articles,
        [],
        [],
        config=RelevanceConfig(enabled=False, keep_labels=[]),
        cache_dir=tmp_path / "cache",
        error_audit_path=tmp_path / "errors.jsonl",
        classifier=classifier,
    )

    assert classifier.calls == []
    assert len(screened.articles_relevant) == 2
    assert {record.relevance_label for record in screened.records} == {"POSSIBLE"}
    assert all(record.eligible_for_downstream for record in screened.records)
    assert {record.reason for record in screened.records} == {"Relevance screening disabled."}


def test_classifier_failure_fails_open_and_is_not_cached(tmp_path: Path) -> None:
    classifier = FailingClassifier()
    kwargs = {
        "config": RelevanceConfig(),
        "cache_dir": tmp_path / "cache",
        "error_audit_path": tmp_path / "errors.jsonl",
        "classifier": classifier,
    }

    first = screen_articles([_article("PMID:1", "1")], [], [], **kwargs)
    second = screen_articles([_article("PMID:1", "1")], [], [], **kwargs)

    assert classifier.calls == 2
    assert first.records[0].relevance_label == "POSSIBLE"
    assert first.records[0].eligible_for_downstream is True
    assert first.records[0].reason == (
        "Relevance classifier unavailable; retained conservatively."
    )
    assert second.records[0].relevance_label == "POSSIBLE"
    assert list((tmp_path / "cache").rglob("*.json")) == []
    errors = (tmp_path / "errors.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(errors) == 2
    assert json.loads(errors[0])["article_id"] == "PMID:1"
    assert "Ollama timed out" in json.loads(errors[0])["error"]


def test_successful_classification_is_reused_from_cache(tmp_path: Path) -> None:
    classifier = CountingClassifier([_result("HIGH")])
    kwargs = {
        "config": RelevanceConfig(),
        "cache_dir": tmp_path / "cache",
        "error_audit_path": tmp_path / "errors.jsonl",
        "classifier": classifier,
    }

    first = screen_articles([_article("PMID:1", "1")], [], [], **kwargs)
    second = screen_articles([_article("PMID:1", "1")], [], [], **kwargs)

    assert len(classifier.calls) == 1
    assert first.records[0].request_hash == second.records[0].request_hash
    assert second.records[0].relevance_label == "HIGH"
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 1


def test_missing_abstract_is_classified_from_remaining_metadata(tmp_path: Path) -> None:
    classifier = CountingClassifier([_result("POSSIBLE")])

    screened = screen_articles(
        [_article("PMID:1", "1", abstract=None)],
        [],
        [],
        config=RelevanceConfig(),
        cache_dir=tmp_path / "cache",
        error_audit_path=tmp_path / "errors.jsonl",
        classifier=classifier,
    )

    assert len(classifier.calls) == 1
    assert classifier.calls[0][0]["abstract"] is None
    assert screened.records[0].relevance_label == "POSSIBLE"
    assert screened.records[0].eligible_for_downstream is True


def test_write_outputs_preserves_input_schemas_for_empty_tables(tmp_path: Path) -> None:
    article_schema = pa.schema(
        [("article_id", pa.string()), ("pmid", pa.string()), ("title", pa.string())]
    )
    section_schema = pa.schema([("article_id", pa.string()), ("text", pa.string())])
    screened = screen_articles(
        [],
        [],
        [],
        config=RelevanceConfig(enabled=False),
        cache_dir=tmp_path / "cache",
        error_audit_path=tmp_path / "errors.jsonl",
        classifier=None,
    )

    write_screen_outputs(
        screened,
        tmp_path / "processed",
        article_schema=article_schema,
        section_schema=section_schema,
    )

    relevance = pq.read_table(tmp_path / "processed/article_relevance.parquet")
    articles = pq.read_table(tmp_path / "processed/articles_relevant.parquet")
    sections = pq.read_table(tmp_path / "processed/article_sections_relevant.parquet")
    assert relevance.schema == RELEVANCE_SCHEMA
    assert relevance.num_rows == 0
    assert articles.schema == article_schema
    assert sections.schema == section_schema
    assert (tmp_path / "processed/article_relevance.csv").read_text(encoding="utf-8").startswith(
        "article_id,"
    )


def test_relevance_summary_keeps_acquisition_metrics_separate(tmp_path: Path) -> None:
    classifier = CountingClassifier([_result("HIGH"), _result("POSSIBLE"), _result("LOW")])
    screened = screen_articles(
        [_article("PMID:1", "1"), _article("PMID:2", "2"), _article("PMID:3", "3")],
        [],
        [],
        config=RelevanceConfig(),
        cache_dir=tmp_path / "cache",
        error_audit_path=tmp_path / "errors.jsonl",
        classifier=classifier,
    )
    acquisition_summary = {"unique_pubmed_pmids": 100, "articles_with_abstracts": 90}

    acquisition_summary.update(
        summarize_relevance_records([record.model_dump() for record in screened.records])
    )

    assert acquisition_summary["unique_pubmed_pmids"] == 100
    assert acquisition_summary["articles_with_abstracts"] == 90
    assert acquisition_summary["candidate_articles"] == 3
    assert acquisition_summary["high_relevance"] == 1
    assert acquisition_summary["possible_relevance"] == 1
    assert acquisition_summary["low_relevance"] == 1
    assert acquisition_summary["articles_retained_downstream"] == 2
    assert acquisition_summary["articles_removed_by_relevance_screening"] == 1


def test_debug_report_has_branch_counts_examples_and_target_pmid_decisions(
    tmp_path: Path,
) -> None:
    articles = [
        _article(
            "PMID:18024065",
            "18024065",
            title="Methylphenidate-associated coronary vasospasm",
        ),
        _article(
            "PMID:18690540",
            "18690540",
            title="Treatment utilization and assertive outreach",
        ),
        _article("PMID:3", "3", title="Rare syndrome natural history"),
    ]
    retrieval = [
        {
            "pmid": "18024065",
            "retrieval_branch": "broad_ndd",
            "matched_search_term": None,
            "mondo_id": None,
            "query_id": "g1",
        },
        {
            "pmid": "18690540",
            "retrieval_branch": "broad_ndd",
            "matched_search_term": None,
            "mondo_id": None,
            "query_id": "g1",
        },
        {
            "pmid": "3",
            "retrieval_branch": "disease",
            "matched_search_term": "Rare syndrome",
            "mondo_id": "MONDO:3",
            "query_id": "d1",
        },
    ]
    classifier = CountingClassifier([_result("LOW"), _result("LOW"), _result("HIGH")])
    screened = screen_articles(
        articles,
        retrieval,
        [],
        config=RelevanceConfig(),
        cache_dir=tmp_path / "cache",
        error_audit_path=tmp_path / "errors.jsonl",
        classifier=classifier,
    )

    report = build_debug_report(articles, screened.records)

    assert "Candidate papers: 3" in report
    assert "Retention %: 33.33" in report
    assert "generic-query papers:\n  HIGH: 0\n  POSSIBLE: 0\n  LOW: 2" in report
    assert "disease-query papers:\n  HIGH: 1\n  POSSIBLE: 0\n  LOW: 0" in report
    assert "Examples HIGH (1 of 1)" in report
    assert "Examples LOW (2 of 2)" in report
    assert "Target PMID 18024065: LOW — rejected" in report
    assert "Target PMID 18690540: LOW — rejected" in report
    assert "Methylphenidate-associated coronary vasospasm" in report
    assert "matched search term: Rare syndrome" in report
    assert "matched disease: MONDO:3" in report
