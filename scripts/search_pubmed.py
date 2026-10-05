#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections import defaultdict

import pyarrow.parquet as pq

from ndd_corpus.config import Settings
from ndd_corpus.diseases.build_catalog import write_parquet
from ndd_corpus.pubmed.query_builder import build_disease_query, build_generic_query
from ndd_corpus.pubmed.search import NcbiSearchBackend, partition_rows, partition_search
from ndd_corpus.utils.http import NcbiClient


def main() -> int:
    settings = Settings.load()
    settings.require_ncbi_credentials()
    terms_path = settings.paths.interim / "diseases/search_terms.parquet"
    term_rows = pq.read_table(terms_path).to_pylist()
    enabled: dict[str, list[str]] = defaultdict(list)
    for row in term_rows:
        if row["use_for_pubmed"]:
            enabled[str(row["mondo_id"])].append(str(row["term"]))
    queries = []
    if settings.pubmed.generic_ndd_query:
        queries.append(build_generic_query())
    if settings.pubmed.disease_name_queries:
        queries.extend(
            build_disease_query(mondo_id, terms)
            for mondo_id, terms in sorted(enabled.items())
        )
    api_key = settings.ncbi_api_key.get_secret_value() if settings.ncbi_api_key else None
    rate = (
        settings.network.requests_per_second_with_key
        if api_key
        else settings.network.requests_per_second_without_key
    )
    all_retrieval = []
    all_manifest = []
    with NcbiClient(
        email=settings.ncbi_email or "",
        tool=settings.project.tool_name,
        api_key=api_key,
        timeout=settings.network.timeout_seconds,
        max_retries=settings.network.max_retries,
        requests_per_second=rate,
    ) as client:
        backend = NcbiSearchBackend(client)
        for index, query in enumerate(queries, start=1):
            partitions = partition_search(
                query,
                settings.pubmed.start_year,
                settings.pubmed.end_year,
                backend=backend,
                limit=settings.pubmed.partition_limit,
            )
            retrieval, manifest = partition_rows(partitions)
            all_retrieval.extend(retrieval)
            all_manifest.extend(manifest)
            print(
                f"[pubmed-search] query {index}/{len(queries)} | "
                f"records={len(retrieval)}"
            )
    if not all_retrieval:
        raise RuntimeError("zero PubMed articles retrieved")
    unique = sorted({str(row["pmid"]) for row in all_retrieval}, key=int)
    write_parquet(all_retrieval, settings.paths.interim / "pubmed/search_results.parquet")
    write_parquet(all_manifest, settings.paths.interim / "pubmed/search_manifest.parquet")
    write_parquet(
        [{"pmid": pmid} for pmid in unique],
        settings.paths.interim / "pubmed/unique_pmids.parquet",
    )
    print(f"[pubmed-search] unique PMIDs={len(unique)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

