#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from ndd_corpus.config import Settings
from ndd_corpus.diseases.build_catalog import write_parquet
from ndd_corpus.pmc.downloader import download_article
from ndd_corpus.pmc.inventory import (
    InventoryEntry,
    filter_inventory,
    parse_inventory_csv,
    parse_inventory_listing,
    parse_inventory_manifest,
    select_version,
)
from ndd_corpus.pmc.parser import parse_jats
from ndd_corpus.utils.checkpoint import CheckpointStore
from ndd_corpus.utils.http import atomic_write_bytes

INVENTORY_PREFIX = "inventory-reports/pmc-oa-opendata/metadata/"


class HttpxDownloader:
    def __init__(self, client: httpx.Client):
        self.client = client

    def get(self, url: str) -> bytes:
        response = self.client.get(url)
        response.raise_for_status()
        return response.content


def _inventory_entries(
    client: httpx.Client, base_url: str, cache_dir: Path
) -> tuple[str, list[InventoryEntry]]:
    listing = client.get(
        f"{base_url}/",
        params={"list-type": "2", "prefix": INVENTORY_PREFIX, "delimiter": "/"},
    )
    listing.raise_for_status()
    snapshot = parse_inventory_listing(listing.content)
    manifest_response = client.get(f"{base_url}/{snapshot}manifest.json")
    manifest_response.raise_for_status()
    manifest = manifest_response.json()
    keys = parse_inventory_manifest(manifest)
    snapshot_name = snapshot.rstrip("/").rsplit("/", 1)[-1]
    snapshot_dir = cache_dir / snapshot_name
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(snapshot_dir / "manifest.json", manifest_response.content)
    entries = []
    for index, key in enumerate(keys):
        cached_csv = snapshot_dir / f"inventory-{index:03d}.csv.gz"
        if cached_csv.is_file():
            content = cached_csv.read_bytes()
        else:
            response = client.get(f"{base_url}/{key}")
            response.raise_for_status()
            content = response.content
            atomic_write_bytes(cached_csv, content)
        entries.extend(parse_inventory_csv(content))
    return snapshot_name, entries


def _write_empty(path: Path, schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist([], schema=schema), path, compression="zstd")


def main() -> int:
    settings = Settings.load()
    mapping = pq.read_table(settings.paths.interim / "pmc/pmid_pmcid.parquet").to_pylist()
    requested = {
        str(row["pmcid"])
        for row in mapping
        if row["mapping_status"] == "mapped" and row.get("pmcid")
    }
    if settings.debug.enabled:
        requested = set(sorted(requested)[: settings.debug.pmc_limit])
    checkpoint = CheckpointStore(settings.paths.interim / "checkpoints.sqlite")
    checkpoint.reset_interrupted()
    cache_dir = settings.paths.raw / "pmc/inventory"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=settings.network.timeout_seconds, follow_redirects=True) as client:
        snapshot, inventory = _inventory_entries(
            client, settings.pmc.inventory_bucket_url, cache_dir
        )
        candidates: dict[str, list[dict[str, object]]] = defaultdict(list)
        metadata_cache = cache_dir / snapshot / "metadata"
        metadata_cache.mkdir(parents=True, exist_ok=True)
        for entry in filter_inventory(inventory, requested):
            metadata_path = metadata_cache / Path(entry.metadata_key).name
            content = metadata_path.read_bytes() if metadata_path.is_file() else b""
            actual = hashlib.md5(content, usedforsecurity=False).hexdigest() if content else ""
            if not content or (entry.etag and actual != entry.etag):
                response = client.get(
                    f"{settings.pmc.inventory_bucket_url}/{entry.metadata_key}"
                )
                response.raise_for_status()
                content = response.content
                atomic_write_bytes(metadata_path, content)
                actual = hashlib.md5(content, usedforsecurity=False).hexdigest()
            if entry.etag and actual != entry.etag:
                raise ValueError(f"PMC metadata ETag mismatch: {entry.metadata_key}")
            metadata = json.loads(content)
            metadata["inventory_snapshot"] = snapshot
            metadata["inventory_last_modified"] = entry.last_modified
            candidates[entry.pmcid].append(metadata)
        selected = [select_version(values) for _pmcid, values in sorted(candidates.items())]
        downloader = HttpxDownloader(client)
        downloads = [
            download_article(
                metadata,
                downloader,
                checkpoint,
                settings.paths.raw / "pmc/articles",
            )
            for metadata in selected
        ]
    articles = []
    sections = []
    for download, metadata in zip(downloads, selected, strict=True):
        xml_path = Path(download["xml_path"])
        article, article_sections = parse_jats(gzip.decompress(xml_path.read_bytes()))
        article.update(
            {
                "pmc_version": metadata["version"],
                "pmc_license": metadata.get("license_code"),
                "is_manuscript": metadata.get("is_manuscript"),
                "is_retracted": metadata.get("is_retracted"),
                "pmc_xml_file": str(xml_path),
            }
        )
        articles.append(article)
        sections.extend(article_sections)
    if downloads:
        download_rows = [
            {
                key: str(value) if isinstance(value, Path) else value
                for key, value in row.items()
            }
            for row in downloads
        ]
        write_parquet(
            download_rows,
            settings.paths.interim / "pmc/download_manifest.parquet",
        )
        write_parquet(selected, settings.paths.interim / "pmc/version_selection.parquet")
        write_parquet(articles, settings.paths.interim / "pmc/articles.parquet")
        if sections:
            write_parquet(sections, settings.paths.interim / "pmc/sections.parquet")
        else:
            _write_empty(
                settings.paths.interim / "pmc/sections.parquet",
                pa.schema(
                    [
                        ("pmcid", pa.string()),
                        ("section_index", pa.int64()),
                        ("text", pa.string()),
                    ]
                ),
            )
    else:
        _write_empty(
            settings.paths.interim / "pmc/download_manifest.parquet",
            pa.schema([("pmcid", pa.string()), ("status", pa.string()), ("xml_path", pa.string())]),
        )
        _write_empty(
            settings.paths.interim / "pmc/version_selection.parquet",
            pa.schema([("pmcid", pa.string()), ("version", pa.int64())]),
        )
        _write_empty(
            settings.paths.interim / "pmc/articles.parquet",
            pa.schema([("pmcid", pa.string()), ("pmid", pa.string()), ("doi", pa.string())]),
        )
        _write_empty(
            settings.paths.interim / "pmc/sections.parquet",
            pa.schema(
                [
                    ("pmcid", pa.string()),
                    ("section_index", pa.int64()),
                    ("text", pa.string()),
                ]
            ),
        )
    print(f"[pmc-download] {len(downloads)}/{len(requested)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
