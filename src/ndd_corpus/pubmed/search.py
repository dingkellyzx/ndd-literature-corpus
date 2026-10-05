from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from ndd_corpus.pubmed.query_builder import SearchQuery
from ndd_corpus.utils.http import NcbiClient

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


@dataclass(frozen=True, order=True, slots=True)
class DateInterval:
    start: date
    end: date

    @property
    def label(self) -> str:
        return f"{self.start.isoformat()}..{self.end.isoformat()}"

    @property
    def is_year(self) -> bool:
        return (
            self.start.month == 1
            and self.start.day == 1
            and self.end.month == 12
            and self.end.day == 31
            and self.start.year == self.end.year
        )

    @property
    def is_month(self) -> bool:
        return (
            self.start.year == self.end.year
            and self.start.month == self.end.month
            and self.start.day == 1
            and self.end.day == calendar.monthrange(self.end.year, self.end.month)[1]
        )


@dataclass(frozen=True, slots=True)
class SearchPartition:
    query: SearchQuery
    interval: DateInterval
    reported_count: int
    pmids: tuple[str, ...]
    retrieved_at: str


class SearchBackend(Protocol):
    def count(self, query: str, interval: DateInterval) -> int: ...

    def ids(self, query: str, interval: DateInterval, expected: int) -> list[str]: ...


class SearchCountMismatch(RuntimeError):
    pass


def dated_query(query: str, interval: DateInterval) -> str:
    return (
        f"({query}) AND "
        f'("{interval.start:%Y/%m/%d}"[Date - Publication] : '
        f'"{interval.end:%Y/%m/%d}"[Date - Publication])'
    )


class NcbiSearchBackend:
    def __init__(self, client: NcbiClient):
        self.client = client

    def _search(self, query: str, interval: DateInterval, *, retmax: int) -> dict[str, object]:
        response = self.client.post(
            ESEARCH_URL,
            data={
                "db": "pubmed",
                "term": dated_query(query, interval),
                "retmode": "json",
                "retmax": str(retmax),
                "sort": "pub_date",
            },
        )
        result = response.json().get("esearchresult")
        if not isinstance(result, dict):
            raise ValueError("NCBI ESearch response lacks esearchresult")
        return result

    def count(self, query: str, interval: DateInterval) -> int:
        value = self._search(query, interval, retmax=0).get("count")
        if not isinstance(value, (str, int)):
            raise ValueError("NCBI ESearch response count is missing or invalid")
        return int(value)

    def ids(self, query: str, interval: DateInterval, expected: int) -> list[str]:
        result = self._search(query, interval, retmax=expected)
        idlist = result.get("idlist", [])
        if not isinstance(idlist, list):
            raise ValueError("NCBI ESearch response idlist is not a list")
        return [str(identifier) for identifier in idlist]


def _months(year: int) -> list[DateInterval]:
    return [
        DateInterval(
            date(year, month, 1),
            date(year, month, calendar.monthrange(year, month)[1]),
        )
        for month in range(1, 13)
    ]


def _days(interval: DateInterval) -> list[DateInterval]:
    return [
        DateInterval(
            date(interval.start.year, interval.start.month, day),
            date(interval.start.year, interval.start.month, day),
        )
        for day in range(1, interval.end.day + 1)
    ]


def _pmid_sort_key(value: str) -> tuple[int, str]:
    return (int(value), value) if value.isdigit() else (2**63 - 1, value)


def partition_search(
    query: SearchQuery,
    start_year: int,
    end_year: int,
    *,
    backend: SearchBackend,
    limit: int = 9_999,
) -> list[SearchPartition]:
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    pending = [
        DateInterval(date(year, 1, 1), date(year, 12, 31))
        for year in range(start_year, end_year + 1)
    ]
    completed: list[SearchPartition] = []
    while pending:
        interval = pending.pop(0)
        reported = backend.count(query.query, interval)
        if reported > limit:
            if interval.is_year:
                pending[0:0] = _months(interval.start.year)
                continue
            if interval.is_month:
                pending[0:0] = _days(interval)
                continue
            raise SearchCountMismatch(
                f"single-day partition exceeds PubMed limit: {interval.label} count={reported}"
            )
        retrieved = backend.ids(query.query, interval, reported) if reported else []
        unique = tuple(sorted(set(retrieved), key=_pmid_sort_key))
        if len(unique) != reported:
            raise SearchCountMismatch(
                f"{query.query_id} {interval.label}: reported={reported} retrieved={len(unique)}"
            )
        completed.append(
            SearchPartition(
                query=query,
                interval=interval,
                reported_count=reported,
                pmids=unique,
                retrieved_at=datetime.now(UTC).isoformat(),
            )
        )
    return sorted(completed, key=lambda part: part.interval)


def partition_rows(
    partitions: list[SearchPartition],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    retrieval: list[dict[str, object]] = []
    manifest: list[dict[str, object]] = []
    for part in partitions:
        manifest.append(
            {
                "query_id": part.query.query_id,
                "query": part.query.query,
                "query_terms": list(part.query.terms),
                "retrieval_branch": part.query.branch,
                "mondo_id": part.query.mondo_id,
                "publication_date_partition": part.interval.label,
                "reported_result_count": part.reported_count,
                "retrieved_unique_pmids": len(part.pmids),
                "retrieved_at": part.retrieved_at,
            }
        )
        retrieval.extend(
            {
                "pmid": pmid,
                "retrieval_branch": part.query.branch,
                "mondo_id": part.query.mondo_id,
                "query_id": part.query.query_id,
                "query": part.query.query,
                "query_terms": list(part.query.terms),
                "matched_search_term": None,
                "publication_date_partition": part.interval.label,
                "retrieved_at": part.retrieved_at,
            }
            for pmid in part.pmids
        )
    return retrieval, manifest
