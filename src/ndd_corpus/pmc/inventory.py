from __future__ import annotations

import csv
import gzip
import io
import re
from dataclasses import dataclass
from typing import Any

from lxml import etree


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    pmcid: str
    version: int
    metadata_key: str
    last_modified: str
    etag: str


def parse_inventory_listing(content: bytes) -> str:
    root = etree.fromstring(
        content,
        parser=etree.XMLParser(resolve_entities=False, no_network=True),
    )
    prefixes = [
        "".join(element.itertext()).strip()
        for element in root.xpath("//*[local-name()='CommonPrefixes']/*[local-name()='Prefix']")
    ]
    prefixes = [prefix for prefix in prefixes if re.search(r"\d{4}-\d{2}-\d{2}T", prefix)]
    if not prefixes:
        raise ValueError("PMC inventory listing contains no dated snapshot")
    return sorted(prefixes)[-1]


def parse_inventory_manifest(payload: dict[str, Any]) -> list[str]:
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("PMC inventory manifest has no files list")
    keys = [str(item["key"]) for item in files if isinstance(item, dict) and item.get("key")]
    if not keys:
        raise ValueError("PMC inventory manifest contains no CSV keys")
    return keys


def parse_inventory_csv(content: bytes) -> list[InventoryEntry]:
    raw = gzip.decompress(content) if content.startswith(b"\x1f\x8b") else content
    rows = csv.reader(io.StringIO(raw.decode("utf-8")))
    entries = []
    pattern = re.compile(r"^metadata/(PMC\d+)\.(\d+)\.json$")
    for row in rows:
        if len(row) < 4:
            continue
        match = pattern.match(row[1])
        if not match:
            continue
        entries.append(
            InventoryEntry(
                pmcid=match.group(1),
                version=int(match.group(2)),
                metadata_key=row[1],
                last_modified=row[2],
                etag=row[3].strip('"'),
            )
        )
    return sorted(entries, key=lambda entry: (entry.pmcid, entry.version))


def filter_inventory(
    entries: list[InventoryEntry], requested_pmcids: set[str]
) -> list[InventoryEntry]:
    return [entry for entry in entries if entry.pmcid in requested_pmcids]


def _truthy(value: object) -> bool:
    return str(value).casefold() in {"1", "true", "yes"}


def select_version(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("cannot select from zero PMC versions")
    non_retracted = [item for item in candidates if not _truthy(item.get("is_retracted"))]
    eligible = non_retracted or candidates
    published = [item for item in eligible if not _truthy(item.get("is_manuscript"))]
    preferred = published or eligible
    chosen = max(preferred, key=lambda item: int(item.get("version", 0)))
    result = dict(chosen)
    if non_retracted and published:
        reason = "non-retracted published version"
    elif non_retracted:
        reason = "non-retracted manuscript"
    elif published:
        reason = "published version; all candidates retracted"
    else:
        reason = "available manuscript; all candidates retracted"
    result["selection_reason"] = reason
    result["all_candidates"] = sorted(candidates, key=lambda item: int(item.get("version", 0)))
    return result

