from __future__ import annotations

from datetime import date

import pytest

from ndd_corpus.pubmed.query_builder import build_disease_query
from ndd_corpus.pubmed.search import (
    DateInterval,
    SearchCountMismatch,
    partition_search,
)


class FakeBackend:
    def __init__(self, counts: dict[tuple[date, date], int], *, mismatch: bool = False):
        self.counts = counts
        self.mismatch = mismatch

    def count(self, _query: str, interval: DateInterval) -> int:
        return self.counts.get((interval.start, interval.end), 0)

    def ids(self, _query: str, interval: DateInterval, expected: int) -> list[str]:
        size = expected - 1 if self.mismatch and expected else expected
        prefix = interval.start.strftime("%Y%m%d")
        return [f"{prefix}{index}" for index in range(size)]


def test_large_year_is_partitioned_by_month_and_reconciled() -> None:
    year = (date(2020, 1, 1), date(2020, 12, 31))
    january = (date(2020, 1, 1), date(2020, 1, 31))
    backend = FakeBackend({year: 12_000, january: 2})
    query = build_disease_query("MONDO:1", ["example syndrome"])

    partitions = partition_search(query, 2020, 2020, backend=backend, limit=9_999)

    assert len(partitions) == 12
    assert partitions[0].interval == DateInterval(*january)
    assert partitions[0].reported_count == 2
    assert len(partitions[0].pmids) == 2
    assert sum(part.reported_count for part in partitions) == 2


def test_large_month_is_partitioned_by_day() -> None:
    year = (date(2020, 1, 1), date(2020, 12, 31))
    january = (date(2020, 1, 1), date(2020, 1, 31))
    first_day = (date(2020, 1, 1), date(2020, 1, 1))
    backend = FakeBackend({year: 20_000, january: 12_000, first_day: 1})
    query = build_disease_query("MONDO:1", ["example syndrome"])

    partitions = partition_search(query, 2020, 2020, backend=backend, limit=9_999)

    assert any(part.interval == DateInterval(*first_day) for part in partitions)
    assert len(partitions) == 42


def test_count_mismatch_fails_partition() -> None:
    year = (date(2020, 1, 1), date(2020, 12, 31))
    query = build_disease_query("MONDO:1", ["example syndrome"])

    with pytest.raises(SearchCountMismatch, match="reported=2 retrieved=1"):
        partition_search(query, 2020, 2020, backend=FakeBackend({year: 2}, mismatch=True))

