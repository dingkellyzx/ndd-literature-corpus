from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationReport:
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"valid": not self.errors, "errors": self.errors, "warnings": self.warnings}

    def raise_for_errors(self) -> None:
        if self.errors:
            codes = ", ".join(str(item["code"]) for item in self.errors)
            raise ValueError(f"corpus validation failed: {codes}")


def _issue(code: str, message: str, **details: object) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details}


def validate_corpus(
    *,
    articles: list[dict[str, Any]],
    search_manifest: list[dict[str, Any]],
    pmc_mapping: list[dict[str, Any]],
    pubmed_download_manifest: list[dict[str, Any]],
    pmc_download_manifest: list[dict[str, Any]],
) -> ValidationReport:
    errors = []
    warnings = []
    if not articles:
        errors.append(_issue("zero_articles", "canonical article table is empty"))
    pmids = [str(row["pmid"]) for row in articles if row.get("pmid")]
    duplicates = sorted(pmid for pmid, count in Counter(pmids).items() if count > 1)
    if duplicates:
        errors.append(
            _issue("duplicate_pmid", "duplicate PMID in canonical table", pmids=duplicates)
        )
    invalid_pmcids = sorted(
        {
            str(row["pmcid"])
            for row in articles
            if row.get("pmcid") and not re.fullmatch(r"PMC\d+", str(row["pmcid"]))
        }
    )
    if invalid_pmcids:
        errors.append(_issue("invalid_pmcid", "invalid PMCID format", pmcids=invalid_pmcids))
    for row in search_manifest:
        if int(row.get("reported_result_count", -1)) != int(
            row.get("retrieved_unique_pmids", -2)
        ):
            errors.append(
                _issue(
                    "search_count_mismatch",
                    "ESearch reported and stored counts differ",
                    query_id=row.get("query_id"),
                )
            )
    mappings: dict[str, set[str]] = defaultdict(set)
    for row in pmc_mapping:
        if row.get("pmid") and row.get("pmcid"):
            mappings[str(row["pmid"])].add(str(row["pmcid"]))
    conflicts = {pmid: sorted(values) for pmid, values in mappings.items() if len(values) > 1}
    if conflicts:
        errors.append(
            _issue(
                "pmid_pmcid_conflict",
                "PMID maps to multiple PMCIDs",
                conflicts=conflicts,
            )
        )
    for manifest_name, manifest in (
        ("pubmed", pubmed_download_manifest),
        ("pmc", pmc_download_manifest),
    ):
        for row in manifest:
            if row.get("status", "complete") != "complete":
                continue
            file_path = row.get("file_path") or row.get("xml_path")
            if file_path and not Path(str(file_path)).is_file():
                errors.append(
                    _issue(
                        "missing_file",
                        f"completed {manifest_name} artifact is missing",
                        file_path=str(file_path),
                    )
                )
    if any(not row.get("has_abstract") for row in articles):
        warnings.append(_issue("missing_abstract", "one or more articles have no abstract"))
    if any(row.get("mapping_status") == "not_in_pmc" for row in pmc_mapping):
        warnings.append(_issue("pmid_without_pmcid", "one or more PMIDs are not in PMC"))
    return ValidationReport(errors=errors, warnings=warnings)


def build_summary(
    *,
    disease_catalog: list[dict[str, Any]],
    search_terms: list[dict[str, Any]],
    articles: list[dict[str, Any]],
    pmc_mapping: list[dict[str, Any]],
    pmc_downloads: list[dict[str, Any]],
) -> dict[str, Any]:
    years = sorted(
        int(row["publication_year"])
        for row in articles
        if row.get("publication_year") is not None
    )
    decade_counts = Counter((year // 10) * 10 for year in years)
    disease_counts: Counter[str] = Counter()
    for article in articles:
        disease_counts.update(str(value) for value in article.get("mondo_ids", []))
    mapped = sum(row.get("mapping_status") == "mapped" for row in pmc_mapping)
    return {
        "mondo_ndd_descendants": len(disease_catalog),
        "rare_ndd_diseases": sum(bool(row.get("is_rare")) for row in disease_catalog),
        "diseases_with_orphanet_mappings": sum(
            bool(row.get("orpha_id")) for row in disease_catalog
        ),
        "search_terms": sum(bool(row.get("use_for_pubmed")) for row in search_terms),
        "excluded_ambiguous_search_terms": sum(
            not bool(row.get("use_for_pubmed")) for row in search_terms
        ),
        "unique_pubmed_pmids": len({str(row["pmid"]) for row in articles if row.get("pmid")}),
        "articles_with_abstracts": sum(bool(row.get("has_abstract")) for row in articles),
        "articles_without_abstracts": sum(not bool(row.get("has_abstract")) for row in articles),
        "pmids_with_pmcids": mapped,
        "pmids_without_pmcids": len(pmc_mapping) - mapped,
        "pmc_xml_successfully_downloaded": sum(
            row.get("status", "complete") == "complete" for row in pmc_downloads
        ),
        "pmc_download_failures": sum(row.get("status") == "failed" for row in pmc_downloads),
        "articles_with_full_text": sum(bool(row.get("has_fulltext")) for row in articles),
        "articles_with_abstract_only": sum(
            bool(row.get("has_abstract")) and not bool(row.get("has_fulltext"))
            for row in articles
        ),
        "publication_year_range": [years[0], years[-1]] if years else None,
        "articles_per_decade": {str(key): decade_counts[key] for key in sorted(decade_counts)},
        "top_diseases_by_retrieved_article_count": [
            {"mondo_id": mondo_id, "article_count": count}
            for mondo_id, count in disease_counts.most_common(20)
        ],
    }
