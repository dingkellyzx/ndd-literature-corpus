#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import UTC, datetime

import httpx

from ndd_corpus.config import Settings
from ndd_corpus.diseases.build_catalog import write_parquet
from ndd_corpus.utils.http import atomic_write_bytes, sha256_file


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
    manifest = []
    with httpx.Client(timeout=settings.network.timeout_seconds, follow_redirects=True) as client:
        for url, destination in downloads:
            response = client.get(url)
            response.raise_for_status()
            atomic_write_bytes(destination, response.content)
            manifest.append(
                {
                    "url": url,
                    "file_path": str(destination),
                    "sha256": sha256_file(destination),
                    "downloaded_at": datetime.now(UTC).isoformat(),
                }
            )
            print(f"[reference] downloaded {destination.name}")
    write_parquet(manifest, settings.paths.interim / "reference_manifest.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())

