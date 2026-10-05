#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ndd_corpus.config import Settings
from ndd_corpus.corpus.merge import merge_corpus
from ndd_corpus.corpus.validate import validate_corpus
from ndd_corpus.diseases.build_catalog import write_parquet
from ndd_corpus.utils.http import atomic_write_bytes


def _read(path: Path, *, optional: bool = False) -> list[dict[str, object]]:
    if optional and not path.is_file():
        return []
    return pq.read_table(path).to_pylist()


def _write_optional(rows: list[dict[str, object]], path: Path, schema: pa.Schema) -> None:
    if rows:
        write_parquet(rows, path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist([], schema=schema), path, compression="zstd")


def main() -> int:
    settings = Settings.load()
    pubmed = _read(settings.paths.interim / "pubmed/articles.parquet")
    pmc = _read(settings.paths.interim / "pmc/articles.parquet", optional=True)
    retrieval = _read(settings.paths.interim / "pubmed/search_results.parquet")
    sections = _read(settings.paths.interim / "pmc/sections.parquet", optional=True)
    result = merge_corpus(pubmed, pmc, retrieval, sections)
    write_parquet(result.articles, settings.paths.processed / "articles.parquet")
    _write_optional(
        result.sections,
        settings.paths.processed / "article_sections.parquet",
        pa.schema(
            [
                ("article_id", pa.string()),
                ("pmcid", pa.string()),
                ("section_index", pa.int64()),
                ("section_title", pa.string()),
                ("section_type", pa.string()),
                ("text", pa.string()),
            ]
        ),
    )
    _write_optional(
        result.disease_retrieval,
        settings.paths.processed / "article_disease_retrieval.parquet",
        pa.schema(
            [
                ("pmid", pa.string()),
                ("mondo_id", pa.string()),
                ("retrieval_branch", pa.string()),
                ("matched_search_term", pa.string()),
                ("query_id", pa.string()),
            ]
        ),
    )
    _write_optional(
        result.deduplication_log,
        settings.paths.interim / "deduplication_log.parquet",
        pa.schema(
            [
                ("record_index", pa.int64()),
                ("group_index", pa.int64()),
                ("match_type", pa.string()),
                ("match_value", pa.string()),
                ("requires_review", pa.bool_()),
            ]
        ),
    )
    report = validate_corpus(
        articles=result.articles,
        search_manifest=_read(settings.paths.interim / "pubmed/search_manifest.parquet"),
        pmc_mapping=_read(settings.paths.interim / "pmc/pmid_pmcid.parquet"),
        pubmed_download_manifest=_read(
            settings.paths.interim / "pubmed/download_manifest.parquet"
        ),
        pmc_download_manifest=_read(
            settings.paths.interim / "pmc/download_manifest.parquet", optional=True
        ),
    )
    validation_path = settings.paths.processed / "validation_report.json"
    atomic_write_bytes(
        validation_path,
        json.dumps(report.to_dict(), indent=2, sort_keys=True).encode("utf-8") + b"\n",
    )
    report.raise_for_errors()
    print(
        f"[corpus] articles={len(result.articles)} | sections={len(result.sections)} | "
        f"warnings={len(report.warnings)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

