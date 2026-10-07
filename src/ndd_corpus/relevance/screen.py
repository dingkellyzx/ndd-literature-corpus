from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq

from ndd_corpus.config import RelevanceConfig
from ndd_corpus.relevance.classifier import OllamaRelevanceClassifier
from ndd_corpus.relevance.models import (
    ArticleRelevanceRecord,
    ClassificationResult,
    RelevanceSignals,
    RetrievalProvenance,
)
from ndd_corpus.relevance.prompt import (
    article_prompt_payload,
    compute_request_hash,
    prompt_sha256,
)
from ndd_corpus.relevance.signals import detect_relevance_signals
from ndd_corpus.utils.http import atomic_write_bytes

RELEVANCE_SCHEMA = pa.schema(
    [
        ("article_id", pa.string()),
        ("pmid", pa.string()),
        ("pmcid", pa.string()),
        ("relevance_label", pa.string()),
        ("eligible_for_downstream", pa.bool_()),
        ("evidence_types", pa.list_(pa.string())),
        ("reason", pa.string()),
        ("positive_signals", pa.list_(pa.string())),
        ("negative_signals", pa.list_(pa.string())),
        ("retrieval_branches", pa.list_(pa.string())),
        ("mondo_ids", pa.list_(pa.string())),
        ("matched_search_terms", pa.list_(pa.string())),
        ("query_ids", pa.list_(pa.string())),
        ("model_id", pa.string()),
        ("prompt_version", pa.string()),
        ("prompt_sha256", pa.string()),
        ("request_hash", pa.string()),
    ]
)


class RelevanceClassifier(Protocol):
    def classify(
        self,
        article: Mapping[str, object],
        provenance: RetrievalProvenance,
        signals: RelevanceSignals,
    ) -> ClassificationResult: ...


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    records: list[ArticleRelevanceRecord]
    articles_relevant: list[dict[str, object]]
    sections_relevant: list[dict[str, object]]
    errors: list[dict[str, object]]

    def counts(self) -> dict[str, int]:
        labels = {"HIGH": 0, "POSSIBLE": 0, "LOW": 0}
        for record in self.records:
            labels[record.relevance_label] += 1
        return {
            "candidate": len(self.records),
            "high": labels["HIGH"],
            "possible": labels["POSSIBLE"],
            "low": labels["LOW"],
            "retained": len(self.articles_relevant),
        }


def _unique_values(rows: Iterable[Mapping[str, object]], field: str) -> list[str]:
    return sorted(
        {
            str(value)
            for row in rows
            if (value := row.get(field)) is not None and str(value)
        },
        key=str.casefold,
    )


def aggregate_retrieval_provenance(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, RetrievalProvenance]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        pmid = row.get("pmid")
        if pmid is not None and str(pmid):
            grouped[str(pmid)].append(row)
    return {
        pmid: RetrievalProvenance(
            retrieval_branches=_unique_values(group, "retrieval_branch"),
            mondo_ids=_unique_values(group, "mondo_id"),
            matched_search_terms=_unique_values(group, "matched_search_term"),
            query_ids=_unique_values(group, "query_id"),
        )
        for pmid, group in grouped.items()
    }


def _cache_path(cache_dir: Path, article_id: str, request_hash: str) -> Path:
    return cache_dir / quote(article_id, safe="") / f"{request_hash}.json"


def _load_cache(path: Path, article_id: str, request_hash: str) -> ClassificationResult | None:
    if not path.is_file():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("article_id") != article_id or cached.get("request_hash") != request_hash:
            return None
        return ClassificationResult.model_validate(cached["classification"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(
    path: Path,
    article_id: str,
    request_hash: str,
    classification: ClassificationResult,
) -> None:
    content = {
        "article_id": article_id,
        "request_hash": request_hash,
        "classification": classification.model_dump(),
    }
    atomic_write_bytes(
        path,
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n",
    )


def _append_errors(path: Path, errors: list[dict[str, object]]) -> None:
    if not errors:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for error in errors:
            handle.write(json.dumps(error, ensure_ascii=False, sort_keys=True) + "\n")


def _identifier(article: Mapping[str, object], field: str) -> str | None:
    value = article.get(field)
    return str(value) if value is not None and str(value) else None


def screen_articles(
    articles: Iterable[Mapping[str, object]],
    retrieval_rows: Iterable[Mapping[str, object]],
    sections: Iterable[Mapping[str, object]],
    *,
    config: RelevanceConfig,
    cache_dir: Path,
    error_audit_path: Path,
    classifier: RelevanceClassifier | None = None,
) -> ScreeningResult:
    article_rows = [dict(row) for row in articles]
    section_rows = [dict(row) for row in sections]
    article_ids = [str(row.get("article_id") or "") for row in article_rows]
    if any(not value for value in article_ids):
        raise ValueError("every article must have a non-empty article_id")
    if len(set(article_ids)) != len(article_ids):
        raise ValueError("article_id values must be unique")

    provenance_by_pmid = aggregate_retrieval_provenance(retrieval_rows)
    actual_prompt_sha = prompt_sha256()
    active_classifier = classifier
    owned_classifier: OllamaRelevanceClassifier | None = None
    if config.enabled and article_rows and active_classifier is None:
        owned_classifier = OllamaRelevanceClassifier(config)
        active_classifier = owned_classifier

    records: list[ArticleRelevanceRecord] = []
    errors: list[dict[str, object]] = []
    try:
        for article, article_id in zip(article_rows, article_ids, strict=True):
            pmid = _identifier(article, "pmid")
            provenance = provenance_by_pmid.get(pmid or "", RetrievalProvenance())
            signals = detect_relevance_signals(
                str(article.get("title") or ""),
                str(article.get("abstract") or ""),
            )
            payload = article_prompt_payload(article, provenance, signals)
            request_hash = compute_request_hash(
                payload,
                model=config.model,
                temperature=config.temperature,
                prompt_version=config.prompt_version,
                actual_prompt_sha256=actual_prompt_sha,
            )
            cache_path = _cache_path(cache_dir, article_id, request_hash)
            failed_open = False
            classification: ClassificationResult
            if not config.enabled:
                classification = ClassificationResult(
                    relevance_label="POSSIBLE",
                    evidence_types=[],
                    reason="Relevance screening disabled.",
                )
                eligible = True
            else:
                cached = _load_cache(cache_path, article_id, request_hash)
                if cached is None:
                    if active_classifier is None:
                        raise RuntimeError("enabled relevance screening has no classifier")
                    try:
                        classification = active_classifier.classify(
                            article, provenance, signals
                        )
                        _write_cache(cache_path, article_id, request_hash, classification)
                    except Exception as error:
                        failed_open = True
                        classification = ClassificationResult(
                            relevance_label="POSSIBLE",
                            evidence_types=[],
                            reason=(
                                "Relevance classifier unavailable; retained conservatively."
                            ),
                        )
                        errors.append(
                            {
                                "article_id": article_id,
                                "pmid": pmid,
                                "error_type": type(error).__name__,
                                "error": str(error),
                                "model_id": config.model,
                                "prompt_version": config.prompt_version,
                                "prompt_sha256": actual_prompt_sha,
                                "request_hash": request_hash,
                            }
                        )
                else:
                    classification = cached
                eligible = failed_open or classification.relevance_label in config.keep_labels
            records.append(
                ArticleRelevanceRecord(
                    article_id=article_id,
                    pmid=pmid,
                    pmcid=_identifier(article, "pmcid"),
                    relevance_label=classification.relevance_label,
                    eligible_for_downstream=eligible,
                    evidence_types=classification.evidence_types,
                    reason=classification.reason,
                    positive_signals=signals.positive_signals,
                    negative_signals=signals.negative_signals,
                    **provenance.model_dump(),
                    model_id=config.model,
                    prompt_version=config.prompt_version,
                    prompt_sha256=actual_prompt_sha,
                    request_hash=request_hash,
                )
            )
    finally:
        if owned_classifier is not None:
            owned_classifier.close()

    _append_errors(error_audit_path, errors)
    eligible_ids = {
        record.article_id for record in records if record.eligible_for_downstream
    }
    return ScreeningResult(
        records=records,
        articles_relevant=[
            row for row in article_rows if str(row["article_id"]) in eligible_ids
        ],
        sections_relevant=[
            row for row in section_rows if str(row.get("article_id") or "") in eligible_ids
        ],
        errors=errors,
    )


def _write_parquet(
    rows: list[dict[str, object]], destination: Path, schema: pa.Schema
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        temporary,
        compression="zstd",
    )
    temporary.replace(destination)


def _csv_value(value: object) -> object:
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_screen_outputs(
    result: ScreeningResult,
    processed_dir: Path,
    *,
    article_schema: pa.Schema,
    section_schema: pa.Schema,
) -> None:
    relevance_rows = [record.model_dump() for record in result.records]
    _write_parquet(
        relevance_rows,
        processed_dir / "article_relevance.parquet",
        RELEVANCE_SCHEMA,
    )
    _write_parquet(
        result.articles_relevant,
        processed_dir / "articles_relevant.parquet",
        article_schema,
    )
    _write_parquet(
        result.sections_relevant,
        processed_dir / "article_sections_relevant.parquet",
        section_schema,
    )
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=RELEVANCE_SCHEMA.names)
    writer.writeheader()
    for row in relevance_rows:
        writer.writerow({key: _csv_value(value) for key, value in row.items()})
    atomic_write_bytes(
        processed_dir / "article_relevance.csv",
        buffer.getvalue().encode("utf-8"),
    )


def summarize_relevance_records(
    records: Iterable[Mapping[str, object]],
) -> dict[str, int]:
    rows = list(records)
    high = sum(row.get("relevance_label") == "HIGH" for row in rows)
    possible = sum(row.get("relevance_label") == "POSSIBLE" for row in rows)
    low = sum(row.get("relevance_label") == "LOW" for row in rows)
    retained = sum(bool(row.get("eligible_for_downstream")) for row in rows)
    return {
        "candidate_articles": len(rows),
        "high_relevance": high,
        "possible_relevance": possible,
        "low_relevance": low,
        "articles_retained_downstream": retained,
        "articles_removed_by_relevance_screening": len(rows) - retained,
    }


def _branch_label_counts(
    records: Iterable[ArticleRelevanceRecord], branch: str
) -> dict[str, int]:
    counts = {"HIGH": 0, "POSSIBLE": 0, "LOW": 0}
    for record in records:
        if branch in record.retrieval_branches:
            counts[record.relevance_label] += 1
    return counts


def _example_lines(
    record: ArticleRelevanceRecord, article: Mapping[str, object]
) -> list[str]:
    return [
        f"- PMID: {record.pmid or '—'}",
        f"  title: {article.get('title') or '—'}",
        f"  retrieval branch: {', '.join(record.retrieval_branches) or '—'}",
        f"  matched disease: {', '.join(record.mondo_ids) or '—'}",
        f"  matched search term: {', '.join(record.matched_search_terms) or '—'}",
        f"  relevance class: {record.relevance_label}",
        f"  evidence types: {', '.join(record.evidence_types) or '—'}",
        f"  reason: {record.reason}",
    ]


def build_debug_report(
    articles: Iterable[Mapping[str, object]],
    records: Iterable[ArticleRelevanceRecord],
    *,
    examples_per_class: int = 10,
) -> str:
    article_by_id = {str(row["article_id"]): row for row in articles}
    record_rows = list(records)
    summary = summarize_relevance_records(record.model_dump() for record in record_rows)
    candidate = summary["candidate_articles"]
    retained = summary["articles_retained_downstream"]
    retention = (100.0 * retained / candidate) if candidate else 0.0
    lines = [
        f"Candidate papers: {candidate}",
        f"HIGH: {summary['high_relevance']}",
        f"POSSIBLE: {summary['possible_relevance']}",
        f"LOW: {summary['low_relevance']}",
        f"Retained papers: {retained}",
        f"Retention %: {retention:.2f}",
        "",
    ]
    # Branch names match ndd_corpus.pubmed.query_builder.
    for heading, branch in (
        ("generic-query papers", "broad_ndd"),
        ("disease-query papers", "disease"),
    ):
        counts = _branch_label_counts(record_rows, branch)
        lines.extend(
            [
                f"{heading}:",
                f"  HIGH: {counts['HIGH']}",
                f"  POSSIBLE: {counts['POSSIBLE']}",
                f"  LOW: {counts['LOW']}",
                "",
            ]
        )
    for label in ("HIGH", "POSSIBLE", "LOW"):
        matches = [record for record in record_rows if record.relevance_label == label]
        examples = matches[:examples_per_class]
        lines.append(f"Examples {label} ({len(examples)} of {len(matches)}):")
        for record in examples:
            lines.extend(_example_lines(record, article_by_id.get(record.article_id, {})))
        if not examples:
            lines.append("- none")
        lines.append("")
    for target in ("18024065", "18690540"):
        target_record = next((item for item in record_rows if item.pmid == target), None)
        if target_record is None:
            lines.extend([f"Target PMID {target}: not present in candidate corpus.", ""])
            continue
        decision = "retained" if target_record.eligible_for_downstream else "rejected"
        article = article_by_id.get(target_record.article_id, {})
        lines.extend(
            [
                f"Target PMID {target}: {target_record.relevance_label} — {decision}",
                f"  title: {article.get('title') or '—'}",
                f"  reason: {target_record.reason}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
