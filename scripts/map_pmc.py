#!/usr/bin/env python3
from __future__ import annotations

import sys

import pyarrow.parquet as pq

from ndd_corpus.config import Settings
from ndd_corpus.diseases.build_catalog import write_parquet
from ndd_corpus.pmc.id_mapping import CachingConverter, PmcIdConverter, map_pmcids
from ndd_corpus.utils.http import NcbiClient


def main() -> int:
    settings = Settings.load()
    settings.require_ncbi_credentials()
    articles = pq.read_table(settings.paths.interim / "pubmed/articles.parquet").to_pylist()
    api_key = settings.ncbi_api_key.get_secret_value() if settings.ncbi_api_key else None
    rate = (
        settings.network.requests_per_second_with_key
        if api_key
        else settings.network.requests_per_second_without_key
    )
    with NcbiClient(
        email=settings.ncbi_email or "",
        tool=settings.project.tool_name,
        api_key=api_key,
        timeout=settings.network.timeout_seconds,
        max_retries=settings.network.max_retries,
        requests_per_second=rate,
    ) as client:
        rows = map_pmcids(
            articles,
            converter=CachingConverter(
                PmcIdConverter(client), settings.paths.interim / "pmc/id_mapping_cache"
            ),
            batch_size=settings.pmc.id_converter_batch_size,
        )
    write_parquet(rows, settings.paths.interim / "pmc/pmid_pmcid.parquet")
    mapped = sum(row["mapping_status"] == "mapped" for row in rows)
    print(f"[pmc-map] {mapped}/{len(rows)} mapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
