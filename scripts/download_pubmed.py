#!/usr/bin/env python3
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pyarrow.parquet as pq

from ndd_corpus.config import Settings
from ndd_corpus.diseases.build_catalog import write_parquet
from ndd_corpus.pubmed.fetch import NcbiFetchBackend, fetch_batches, plan_batches
from ndd_corpus.pubmed.parser import parse_pubmed_xml
from ndd_corpus.utils.checkpoint import CheckpointStore
from ndd_corpus.utils.http import NcbiClient


def main() -> int:
    settings = Settings.load()
    settings.require_ncbi_credentials()
    rows = pq.read_table(settings.paths.interim / "pubmed/unique_pmids.parquet").to_pylist()
    pmids = [str(row["pmid"]) for row in rows]
    if settings.debug.enabled:
        pmids = pmids[: settings.debug.pubmed_limit]
    plans = plan_batches(pmids, batch_size=settings.pubmed.batch_size)
    checkpoint = CheckpointStore(settings.paths.interim / "checkpoints.sqlite")
    checkpoint.reset_interrupted()
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
        manifest = fetch_batches(
            plans,
            backend=NcbiFetchBackend(client),
            checkpoint=checkpoint,
            output_dir=settings.paths.raw / "pubmed/batches",
        )
    articles = []
    for batch in manifest:
        path = Path(str(batch["file_path"]))
        for article in parse_pubmed_xml(gzip.decompress(path.read_bytes())):
            article["pubmed_raw_file"] = str(path)
            articles.append(article)
    if not articles:
        raise RuntimeError("zero PubMed articles parsed")
    write_parquet(manifest, settings.paths.interim / "pubmed/download_manifest.parquet")
    write_parquet(articles, settings.paths.interim / "pubmed/articles.parquet")
    print(f"[pubmed-fetch] batches={len(manifest)} | articles={len(articles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

