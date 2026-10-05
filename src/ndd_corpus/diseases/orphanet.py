from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OrphaRecord:
    orpha_id: str
    preferred_name: str
    synonyms: tuple[str, ...]
    mondo_ids: tuple[str, ...]
    omim_ids: tuple[str, ...]
    mesh_ids: tuple[str, ...]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("#text", "label", "Name", "name"):
            if value.get(key):
                return str(value[key]).strip()
        return ""
    return str(value).strip() if value is not None else ""


def _find_disorders(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "Disorder" in value:
            return [item for item in _as_list(value["Disorder"]) if isinstance(item, dict)]
        for key, nested in value.items():
            if "disorderlist" in key.casefold():
                found = _find_disorders(nested)
                if found:
                    return found
        for nested in value.values():
            found = _find_disorders(nested)
            if found:
                return found
    return []


def _prefixed(prefix: str, value: str) -> str:
    clean = value.strip()
    clean = clean.split(":", 1)[-1]
    if prefix == "MONDO":
        clean = clean.removeprefix("MONDO_").zfill(7)
    return f"{prefix}:{clean}"


def parse_orphadata(payload: dict[str, Any]) -> list[OrphaRecord]:
    records: list[OrphaRecord] = []
    for disorder in _find_disorders(payload):
        code = _text(disorder.get("OrphaCode") or disorder.get("ORPHAcode"))
        if not code:
            continue
        synonym_container = disorder.get("SynonymList", {})
        synonyms = []
        if isinstance(synonym_container, dict):
            synonyms = [_text(item) for item in _as_list(synonym_container.get("Synonym"))]
        reference_container = disorder.get("ExternalReferenceList", {})
        references = []
        if isinstance(reference_container, dict):
            references = _as_list(reference_container.get("ExternalReference"))
        identifiers: dict[str, set[str]] = {"MONDO": set(), "OMIM": set(), "MESH": set()}
        for reference in references:
            if not isinstance(reference, dict):
                continue
            source = _text(reference.get("Source")).upper()
            target = _text(reference.get("Reference"))
            if source in identifiers and target:
                identifiers[source].add(_prefixed("MeSH" if source == "MESH" else source, target))
        records.append(
            OrphaRecord(
                orpha_id=_prefixed("ORPHA", code),
                preferred_name=_text(disorder.get("Name")),
                synonyms=tuple(sorted({value for value in synonyms if value}, key=str.casefold)),
                mondo_ids=tuple(sorted(identifiers["MONDO"])),
                omim_ids=tuple(sorted(identifiers["OMIM"])),
                mesh_ids=tuple(sorted(identifiers["MESH"])),
            )
        )
    return sorted(records, key=lambda record: record.orpha_id)

