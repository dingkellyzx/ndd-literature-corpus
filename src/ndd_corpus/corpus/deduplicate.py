from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^\w]+", " ", normalized.casefold()).split())


def normalize_doi(value: str) -> str:
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        normalized = normalized.removeprefix(prefix)
    return normalized


def _identifiers(record: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    if record.get("pmid"):
        values.append(("pmid", str(record["pmid"])))
    pmcid = record.get("pmcid") or record.get("pmcid_if_present")
    if pmcid:
        values.append(("pmcid", str(pmcid).upper()))
    if record.get("doi"):
        values.append(("doi", normalize_doi(str(record["doi"]))))
    return values


def deduplicate_records(
    records: list[dict[str, Any]],
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    identifier_index: dict[tuple[str, str], int] = {}
    title_index: dict[str, int] = {}
    decisions: list[dict[str, Any]] = []
    for record_index, record in enumerate(records):
        identifiers = _identifiers(record)
        matches = {identifier_index[value] for value in identifiers if value in identifier_index}
        match_type: str | None = None
        if len(matches) > 1:
            raise ValueError(
                f"conflicting identifiers connect multiple article groups: {identifiers}"
            )
        if matches:
            group_index = matches.pop()
            match_type = next(
                kind
                for kind, value in identifiers
                if identifier_index.get((kind, value)) == group_index
            )
        elif not identifiers and record.get("title"):
            title_key = normalize_title(str(record["title"]))
            group_index = title_index.get(title_key, -1)
            if group_index >= 0:
                match_type = "normalized_title"
            else:
                group_index = len(groups)
                groups.append([])
                title_index[title_key] = group_index
        else:
            group_index = len(groups)
            groups.append([])
        if match_type:
            decisions.append(
                {
                    "record_index": record_index,
                    "group_index": group_index,
                    "match_type": match_type,
                    "match_value": (
                        normalize_title(str(record["title"]))
                        if match_type == "normalized_title"
                        else next(value for kind, value in identifiers if kind == match_type)
                    ),
                    "requires_review": match_type == "normalized_title",
                }
            )
        groups[group_index].append(record)
        for identifier in identifiers:
            existing = identifier_index.get(identifier)
            if existing is not None and existing != group_index:
                raise ValueError(f"identifier conflict: {identifier}")
            identifier_index[identifier] = group_index
        if not identifiers and record.get("title"):
            title_index.setdefault(normalize_title(str(record["title"])), group_index)
    return groups, decisions
