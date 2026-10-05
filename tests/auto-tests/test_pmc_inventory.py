from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from ndd_corpus.pmc.downloader import download_article
from ndd_corpus.pmc.inventory import (
    InventoryEntry,
    filter_inventory,
    parse_inventory_csv,
    parse_inventory_listing,
    select_version,
)
from ndd_corpus.utils.checkpoint import CheckpointStore


def test_latest_inventory_is_selected_from_s3_listing() -> None:
    listing = b"""<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <CommonPrefixes><Prefix>inventory-reports/pmc-oa-opendata/metadata/2026-09-01T01-00Z/</Prefix></CommonPrefixes>
      <CommonPrefixes><Prefix>inventory-reports/pmc-oa-opendata/metadata/2026-10-04T01-00Z/</Prefix></CommonPrefixes>
    </ListBucketResult>"""

    assert parse_inventory_listing(listing).endswith("2026-10-04T01-00Z/")


def test_inventory_csv_matches_versions_without_assuming_version_one() -> None:
    csv_bytes = gzip.compress(
        b'"pmc-oa-opendata","metadata/PMC10.2.json","2026-10-01T00:00:00Z","etag10"\n'
        b'"pmc-oa-opendata","metadata/PMC20.1.json","2026-10-01T00:00:00Z","etag20"\n'
    )

    entries = parse_inventory_csv(csv_bytes)
    matched = filter_inventory(entries, {"PMC10"})

    assert matched == [
        InventoryEntry(
            pmcid="PMC10",
            version=2,
            metadata_key="metadata/PMC10.2.json",
            last_modified="2026-10-01T00:00:00Z",
            etag="etag10",
        )
    ]


def test_version_selection_prefers_non_retracted_published_article() -> None:
    candidates = [
        {"pmcid": "PMC10", "version": 1, "is_manuscript": "yes", "is_retracted": "no"},
        {"pmcid": "PMC10", "version": 2, "is_manuscript": "no", "is_retracted": "no"},
        {"pmcid": "PMC10", "version": 3, "is_manuscript": "no", "is_retracted": "yes"},
    ]

    selected = select_version(candidates)

    assert selected["version"] == 2
    assert selected["selection_reason"] == "non-retracted published version"
    assert len(selected["all_candidates"]) == 3


def test_xml_download_validates_md5_and_resumes(tmp_path: Path) -> None:
    xml = b"<article><front/></article>"
    digest = hashlib.md5(xml).hexdigest()  # noqa: S324 - upstream PMC checksum format
    metadata = {
        "pmcid": "PMC10",
        "version": 2,
        "xml_url": f"https://example.test/PMC10.2.xml?md5={digest}",
    }

    class Downloader:
        calls = 0

        def get(self, _url: str) -> bytes:
            self.calls += 1
            return xml

    downloader = Downloader()
    checkpoint = CheckpointStore(tmp_path / "checkpoint.sqlite")

    first = download_article(metadata, downloader, checkpoint, tmp_path / "articles")
    second = download_article(metadata, downloader, checkpoint, tmp_path / "articles")

    assert first == second
    assert downloader.calls == 1
    assert gzip.decompress(first["xml_path"].read_bytes()) == xml


def test_xml_download_rejects_bad_md5(tmp_path: Path) -> None:
    metadata = {
        "pmcid": "PMC10",
        "version": 2,
        "xml_url": "https://example.test/PMC10.2.xml?md5=00000000000000000000000000000000",
    }

    class Downloader:
        def get(self, _url: str) -> bytes:
            return b"<article/>"

    with pytest.raises(ValueError, match="MD5"):
        download_article(
            metadata,
            Downloader(),
            CheckpointStore(tmp_path / "checkpoint.sqlite"),
            tmp_path / "articles",
        )

