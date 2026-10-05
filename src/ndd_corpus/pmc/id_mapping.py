from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from ndd_corpus.utils.http import NcbiClient, atomic_write_bytes

ID_CONVERTER_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"


class Converter(Protocol):
    def convert(self, pmids: tuple[str, ...]) -> list[dict[str, str]]: ...


class PmcIdConverter:
    def __init__(self, client: NcbiClient):
        self.client = client

    def convert(self, pmids: tuple[str, ...]) -> list[dict[str, str]]:
        if len(pmids) > 200:
            raise ValueError("PMC ID Converter accepts at most 200 identifiers")
        response = self.client.get(
            ID_CONVERTER_URL,
            params={"ids": ",".join(pmids), "format": "json"},
        )
        records = response.json().get("records", [])
        if not isinstance(records, list):
            raise ValueError("PMC ID Converter response records is not a list")
        return [
            {str(key): str(value) for key, value in record.items()}
            for record in records
            if isinstance(record, dict)
        ]


class CachingConverter:
    def __init__(self, converter: Converter, cache_dir: str | Path):
        self.converter = converter
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def convert(self, pmids: tuple[str, ...]) -> list[dict[str, str]]:
        key = hashlib.sha256(",".join(pmids).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
                return [
                    {str(name): str(value) for name, value in item.items()}
                    for item in payload
                ]
        records = self.converter.convert(pmids)
        atomic_write_bytes(
            path,
            json.dumps(records, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        )
        return records


def _chunks(values: list[str], size: int) -> Iterable[tuple[str, ...]]:
    for offset in range(0, len(values), size):
        yield tuple(values[offset : offset + size])


def map_pmcids(
    articles: Iterable[dict[str, Any]],
    *,
    converter: Converter,
    batch_size: int = 200,
) -> list[dict[str, str | None]]:
    if not 0 < batch_size <= 200:
        raise ValueError("batch_size must be between 1 and 200")
    inputs = list(articles)
    output: dict[str, dict[str, str | None]] = {}
    unresolved = []
    for article in inputs:
        pmid = str(article["pmid"])
        pmcid = article.get("pmcid_if_present")
        doi = article.get("doi")
        if pmcid:
            output[pmid] = {
                "pmid": pmid,
                "pmcid": str(pmcid),
                "doi": str(doi) if doi else None,
                "mapping_source": "pubmed",
                "mapping_status": "mapped",
            }
        else:
            unresolved.append(pmid)
    for batch in _chunks(unresolved, batch_size):
        converted = {record.get("pmid"): record for record in converter.convert(batch)}
        for pmid in batch:
            record = converted.get(pmid)
            if record and record.get("status") == "error":
                status = "failed"
            elif record and record.get("pmcid"):
                status = "mapped"
            else:
                status = "not_in_pmc"
            output[pmid] = {
                "pmid": pmid,
                "pmcid": record.get("pmcid") if record and status == "mapped" else None,
                "doi": record.get("doi") if record and status == "mapped" else None,
                "mapping_source": "pmc_id_converter",
                "mapping_status": status,
            }
    return [output[str(article["pmid"])] for article in inputs]
