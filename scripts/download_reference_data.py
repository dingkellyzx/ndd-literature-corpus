#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import UTC, datetime

import httpx
import pyarrow.parquet as pq

from ndd_corpus.config import Settings
from ndd_corpus.diseases.build_catalog import write_parquet
from ndd_corpus.utils.http import ensure_download


def main() -> int:
    settings = Settings.load()
    downloads = [
        (settings.reference.mondo_url, settings.paths.raw / "reference/mondo/mondo.json"),
        (
            settings.reference.mondo_rare_url,
            settings.paths.raw / "reference/mondo/mondo-rare.json",
        ),
        (
            settings.reference.orphanet_url,
            settings.paths.raw / "reference/orphanet/en_product1.json.tar.gz",
        ),
    ]
    manifest_path = settings.paths.interim / "reference_manifest.parquet"
    existing = pq.read_table(manifest_path).to_pylist() if manifest_path.is_file() else []
    known_checksums = {str(row["url"]): str(row["sha256"]) for row in existing}
    manifest = []
    with httpx.Client(timeout=settings.network.timeout_seconds, follow_redirects=True) as client:
        for url, destination in downloads:
            def fetch(url: str = url) -> bytes:
                response = client.get(url)
                response.raise_for_status()
                return response.content

            result = ensure_download(
                destination,
                fetch,
                expected_sha256=known_checksums.get(url),
            )
            manifest.append(
                {
                    "url": url,
                    "file_path": str(destination),
                    "sha256": result.sha256,
                    "status": "complete",
                    "downloaded_at": datetime.now(UTC).isoformat(),
                }
            )
            action = "downloaded" if result.downloaded else "reused"
            print(f"[reference] {action} {destination.name}")
    write_parquet(manifest, manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
