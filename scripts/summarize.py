#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

from ndd_corpus.config import Settings
from ndd_corpus.corpus.validate import build_summary
from ndd_corpus.utils.http import atomic_write_bytes


def _read(path: Path, *, optional: bool = False) -> list[dict[str, object]]:
    if optional and not path.is_file():
        return []
    return pq.read_table(path).to_pylist()


def _human_report(summary: dict[str, object]) -> str:
    labels = [
        ("MONDO NDD descendants", "mondo_ndd_descendants"),
        ("Rare NDD diseases", "rare_ndd_diseases"),
        ("Diseases with Orphanet mappings", "diseases_with_orphanet_mappings"),
        ("Search terms", "search_terms"),
        ("Excluded ambiguous search terms", "excluded_ambiguous_search_terms"),
        ("Unique PubMed PMIDs", "unique_pubmed_pmids"),
        ("Articles with abstracts", "articles_with_abstracts"),
        ("Articles without abstracts", "articles_without_abstracts"),
        ("PMIDs with PMCIDs", "pmids_with_pmcids"),
        ("PMIDs without PMCIDs", "pmids_without_pmcids"),
        ("PMC XML successfully downloaded", "pmc_xml_successfully_downloaded"),
        ("PMC download failures", "pmc_download_failures"),
        ("Articles with full text", "articles_with_full_text"),
        ("Articles with abstract only", "articles_with_abstract_only"),
        ("Publication year range", "publication_year_range"),
        ("Articles per decade", "articles_per_decade"),
        ("Top diseases by retrieved article count", "top_diseases_by_retrieved_article_count"),
    ]
    return "\n".join(f"{label}: {summary[key]}" for label, key in labels) + "\n"


def main() -> int:
    settings = Settings.load()
    summary = build_summary(
        disease_catalog=_read(settings.paths.processed / "disease_catalog.parquet"),
        search_terms=_read(settings.paths.interim / "diseases/search_terms.parquet"),
        articles=_read(settings.paths.processed / "articles.parquet"),
        pmc_mapping=_read(settings.paths.interim / "pmc/pmid_pmcid.parquet"),
        pmc_downloads=_read(
            settings.paths.interim / "pmc/download_manifest.parquet", optional=True
        ),
    )
    summary["mondo_ndd_descendants"] = len(
        _read(settings.paths.interim / "diseases/mondo_ndd_descendants.parquet")
    )
    atomic_write_bytes(
        settings.paths.processed / "corpus_summary.json",
        json.dumps(summary, indent=2, sort_keys=True).encode("utf-8") + b"\n",
    )
    report = _human_report(summary)
    atomic_write_bytes(
        settings.paths.processed / "corpus_summary.txt",
        report.encode("utf-8"),
    )
    print(report, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
