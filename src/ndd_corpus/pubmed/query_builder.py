from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchQuery:
    query_id: str
    query: str
    branch: str
    mondo_id: str | None
    terms: tuple[str, ...]


def _stable_terms(terms: Iterable[str]) -> tuple[str, ...]:
    selected: dict[str, str] = {}
    for term in terms:
        clean = " ".join(term.split())
        if clean:
            selected.setdefault(clean.casefold(), clean)
    return tuple(selected[key] for key in sorted(selected))


def _quoted(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"[Title/Abstract]'


def _query_id(branch: str, mondo_id: str | None, query: str) -> str:
    canonical = json.dumps(
        {"branch": branch, "mondo_id": mondo_id, "query": query},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:20]


def build_disease_query(mondo_id: str, terms: Iterable[str]) -> SearchQuery:
    stable = _stable_terms(terms)
    if not stable:
        raise ValueError(f"no enabled PubMed terms for {mondo_id}")
    query = f"({' OR '.join(_quoted(term) for term in stable)})"
    return SearchQuery(
        query_id=_query_id("disease", mondo_id, query),
        query=query,
        branch="disease",
        mondo_id=mondo_id,
        terms=stable,
    )


def build_generic_query() -> SearchQuery:
    mesh = '"Neurodevelopmental Disorders"[MeSH Terms]'
    terms = (
        "neurodevelopmental disorder",
        "developmental encephalopathy",
        "global developmental delay",
        "intellectual disability",
    )
    query = f"({mesh} OR {' OR '.join(_quoted(term) for term in terms)})"
    return SearchQuery(
        query_id=_query_id("broad_ndd", None, query),
        query=query,
        branch="broad_ndd",
        mondo_id=None,
        terms=terms,
    )

