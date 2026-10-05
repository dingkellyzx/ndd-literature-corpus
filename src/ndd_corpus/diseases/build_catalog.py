from __future__ import annotations

import json
import re
import tarfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ndd_corpus.diseases.mondo import MondoGraph, descendants
from ndd_corpus.diseases.orphanet import OrphaRecord

GENERIC_TERMS = {
    "developmental disorder",
    "neurodevelopmental disorder",
    "neurological disorder",
    "rare disease",
    "syndrome",
}


def _xref_values(xrefs: Iterable[str], prefix: str) -> list[str]:
    wanted = prefix.casefold() + ":"
    return sorted({value for value in xrefs if value.casefold().startswith(wanted)})


def build_catalog(
    graph: MondoGraph,
    *,
    root: str,
    rare_only: bool,
    orphanet_records: Iterable[OrphaRecord],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    orpha_by_mondo: dict[str, list[OrphaRecord]] = {}
    for record in orphanet_records:
        for mondo_id in record.mondo_ids:
            orpha_by_mondo.setdefault(mondo_id, []).append(record)
    complete: list[dict[str, Any]] = []
    catalog: list[dict[str, Any]] = []
    for node in descendants(graph, root):
        base = {
            "mondo_id": node.mondo_id,
            "name": node.name,
            "exact_synonyms": list(node.exact_synonyms),
            "narrow_synonyms": list(node.narrow_synonyms),
            "related_synonyms": list(node.related_synonyms),
            "xrefs": list(node.xrefs),
            "parents": list(node.parents),
            "is_rare": node.is_rare,
        }
        complete.append(base)
        if rare_only and not node.is_rare:
            continue
        matched = sorted(orpha_by_mondo.get(node.mondo_id, []), key=lambda item: item.orpha_id)
        orpha = matched[0] if matched else None
        orpha_synonyms = list(orpha.synonyms) if orpha else []
        synonyms = sorted(
            set(node.exact_synonyms) | set(node.narrow_synonyms) | set(orpha_synonyms),
            key=str.casefold,
        )
        omim = set(_xref_values(node.xrefs, "OMIM"))
        mesh = set(_xref_values(node.xrefs, "MESH"))
        if orpha:
            omim.update(orpha.omim_ids)
            mesh.update(orpha.mesh_ids)
        catalog.append(
            {
                "disease_id": node.mondo_id,
                "mondo_id": node.mondo_id,
                "orpha_id": orpha.orpha_id if orpha else None,
                "preferred_name": node.name,
                "synonyms": synonyms,
                "omim_ids": sorted(omim),
                "mesh_ids": sorted(mesh),
                "source": ["MONDO"] + (["Orphanet"] if orpha else []),
                "is_rare": node.is_rare,
                "mondo_exact_synonyms": list(node.exact_synonyms),
                "mondo_narrow_synonyms": list(node.narrow_synonyms),
                "orphanet_preferred_name": orpha.preferred_name if orpha else None,
                "orphanet_synonyms": orpha_synonyms,
            }
        )
    return complete, sorted(catalog, key=lambda row: str(row["mondo_id"]))


def _exclusion_reason(term: str) -> str | None:
    stripped = term.strip()
    if len(stripped) < 4:
        return "too_short"
    if stripped.isnumeric():
        return "numeric_only"
    if len(stripped) <= 3 and re.fullmatch(r"[A-Z0-9-]+", stripped):
        return "short_acronym"
    if stripped.casefold() in GENERIC_TERMS:
        return "generic"
    return None


def build_search_terms(catalog: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for disease in catalog:
        candidates: list[tuple[str, str, str]] = [
            (str(disease["preferred_name"]), "preferred_name", "MONDO")
        ]
        candidates.extend(
            (term, "exact_synonym", "MONDO")
            for term in disease.get("mondo_exact_synonyms", [])
        )
        candidates.extend(
            (term, "narrow_synonym", "MONDO")
            for term in disease.get("mondo_narrow_synonyms", [])
        )
        if disease.get("orphanet_preferred_name"):
            candidates.append(
                (str(disease["orphanet_preferred_name"]), "preferred_name", "Orphanet")
            )
        candidates.extend(
            (term, "synonym", "Orphanet") for term in disease.get("orphanet_synonyms", [])
        )
        seen: set[str] = set()
        for term, term_type, source in candidates:
            clean = " ".join(term.split())
            key = clean.casefold()
            if not clean or key in seen:
                continue
            seen.add(key)
            reason = _exclusion_reason(clean)
            rows.append(
                {
                    "mondo_id": disease["mondo_id"],
                    "term": clean,
                    "term_type": term_type,
                    "source": source,
                    "use_for_pubmed": reason is None,
                    "exclusion_reason": reason,
                }
            )
    return sorted(rows, key=lambda row: (str(row["mondo_id"]), str(row["term"]).casefold()))


def read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(source, "r:gz") as archive:
            members = [member for member in archive.getmembers() if member.name.endswith(".json")]
            if len(members) != 1:
                raise ValueError(f"expected one JSON file in {source}, found {len(members)}")
            handle = archive.extractfile(members[0])
            if handle is None:
                raise ValueError(f"cannot read JSON member in {source}")
            value = json.load(handle)
    else:
        value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {source}")
    return value


def write_parquet(rows: list[dict[str, Any]], path: str | Path) -> Path:
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    pq.write_table(pa.Table.from_pylist(rows), temporary, compression="zstd")
    temporary.replace(destination)
    return destination

