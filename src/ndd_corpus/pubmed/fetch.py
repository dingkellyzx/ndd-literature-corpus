from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lxml import etree

from ndd_corpus.utils.checkpoint import CheckpointStore
from ndd_corpus.utils.http import NcbiClient, atomic_write_bytes, sha256_file

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


@dataclass(frozen=True, slots=True)
class BatchPlan:
    batch_id: str
    pmids: tuple[str, ...]


class FetchBackend(Protocol):
    def fetch(self, pmids: tuple[str, ...]) -> bytes: ...


class NcbiFetchBackend:
    def __init__(self, client: NcbiClient):
        self.client = client

    def fetch(self, pmids: tuple[str, ...]) -> bytes:
        response = self.client.post(
            EFETCH_URL,
            data={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
        )
        return response.content


def _pmid_key(value: str) -> tuple[int, str]:
    return (int(value), value) if value.isdigit() else (2**63 - 1, value)


def plan_batches(pmids: list[str], *, batch_size: int) -> list[BatchPlan]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    ordered = sorted(set(pmids), key=_pmid_key)
    plans: list[BatchPlan] = []
    for offset in range(0, len(ordered), batch_size):
        values = tuple(ordered[offset : offset + batch_size])
        digest = hashlib.sha256(",".join(values).encode()).hexdigest()[:12]
        plans.append(BatchPlan(f"batch_{len(plans) + 1:06d}_{digest}", values))
    return plans


def fetch_batches(
    plans: list[BatchPlan],
    *,
    backend: FetchBackend,
    checkpoint: CheckpointStore,
    output_dir: str | Path,
) -> list[dict[str, object]]:
    destination_dir = Path(output_dir)
    manifest: list[dict[str, object]] = []
    for plan in plans:
        destination = destination_dir / f"{plan.batch_id}.xml.gz"
        checkpoint.ensure_task("pubmed-fetch", plan.batch_id)
        if not checkpoint.is_complete("pubmed-fetch", plan.batch_id):
            if not checkpoint.claim("pubmed-fetch", plan.batch_id):
                continue
            try:
                xml = backend.fetch(plan.pmids)
                etree.fromstring(
                    xml,
                    parser=etree.XMLParser(resolve_entities=False, no_network=True),
                )
                atomic_write_bytes(destination, gzip.compress(xml, mtime=0))
                checkpoint.complete(
                    "pubmed-fetch",
                    plan.batch_id,
                    artifact_path=destination,
                    checksum=sha256_file(destination),
                )
            except BaseException as error:
                checkpoint.fail("pubmed-fetch", plan.batch_id, str(error))
                raise
        manifest.append(
            {
                "batch_id": plan.batch_id,
                "first_pmid": plan.pmids[0],
                "last_pmid": plan.pmids[-1],
                "n_pmids": len(plan.pmids),
                "status": "complete",
                "file_path": str(destination),
                "sha256": sha256_file(destination),
            }
        )
    return manifest
