#!/usr/bin/env python3
from __future__ import annotations

import sys

import pyarrow.parquet as pq

from ndd_corpus.config import Settings
from ndd_corpus.relevance.screen import (
    build_debug_report,
    screen_articles,
    write_screen_outputs,
)
from ndd_corpus.utils.http import atomic_write_bytes


def main() -> int:
    settings = Settings.load()
    articles_table = pq.read_table(settings.paths.processed / "articles.parquet")
    retrieval_table = pq.read_table(
        settings.paths.processed / "article_disease_retrieval.parquet"
    )
    sections_table = pq.read_table(
        settings.paths.processed / "article_sections.parquet"
    )
    relevance_dir = settings.paths.interim / "relevance"
    result = screen_articles(
        articles_table.to_pylist(),
        retrieval_table.to_pylist(),
        sections_table.to_pylist(),
        config=settings.relevance,
        cache_dir=relevance_dir / "cache",
        error_audit_path=relevance_dir / "errors.jsonl",
    )
    write_screen_outputs(
        result,
        settings.paths.processed,
        article_schema=articles_table.schema,
        section_schema=sections_table.schema,
    )
    atomic_write_bytes(
        settings.paths.processed / "relevance_debug_report.txt",
        build_debug_report(articles_table.to_pylist(), result.records).encode("utf-8"),
    )
    counts = result.counts()
    print(
        "[relevance] "
        f"candidate={counts['candidate']} high={counts['high']} "
        f"possible={counts['possible']} low={counts['low']} "
        f"retained={counts['retained']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
