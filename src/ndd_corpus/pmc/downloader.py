from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

from lxml import etree

from ndd_corpus.utils.checkpoint import CheckpointStore
from ndd_corpus.utils.http import atomic_write_bytes, sha256_file


class Downloader(Protocol):
    def get(self, url: str) -> bytes: ...


def _expected_md5(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("md5")
    return values[0].casefold() if values else None


def download_article(
    metadata: dict[str, Any],
    downloader: Downloader,
    checkpoint: CheckpointStore,
    output_dir: str | Path,
) -> dict[str, Any]:
    pmcid = str(metadata["pmcid"])
    version = int(metadata["version"])
    xml_url = str(metadata.get("xml_url") or "")
    if not xml_url:
        raise ValueError(f"PMC metadata has no xml_url: {pmcid}.{version}")
    task_key = f"{pmcid}.{version}"
    article_dir = Path(output_dir) / pmcid
    metadata_path = article_dir / "metadata.json"
    xml_path = article_dir / "article.xml.gz"
    checkpoint.ensure_task("pmc-download", task_key)
    if not checkpoint.is_complete("pmc-download", task_key):
        if not checkpoint.claim("pmc-download", task_key):
            raise RuntimeError(f"PMC download task is already running: {task_key}")
        try:
            xml = downloader.get(xml_url)
            expected = _expected_md5(xml_url)
            actual = hashlib.md5(xml, usedforsecurity=False).hexdigest()
            if expected and actual != expected:
                raise ValueError(f"PMC XML MD5 mismatch for {task_key}")
            etree.fromstring(
                xml,
                parser=etree.XMLParser(resolve_entities=False, no_network=True),
            )
            atomic_write_bytes(
                metadata_path,
                json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8") + b"\n",
            )
            atomic_write_bytes(xml_path, gzip.compress(xml, mtime=0))
            checkpoint.complete(
                "pmc-download",
                task_key,
                artifact_path=xml_path,
                checksum=sha256_file(xml_path),
            )
        except BaseException as error:
            checkpoint.fail("pmc-download", task_key, str(error))
            raise
    if not metadata_path.is_file():
        raise FileNotFoundError(f"completed PMC metadata is missing: {metadata_path}")
    return {
        "pmcid": pmcid,
        "selected_version": version,
        "metadata_path": metadata_path,
        "xml_path": xml_path,
        "sha256": sha256_file(xml_path),
    }

