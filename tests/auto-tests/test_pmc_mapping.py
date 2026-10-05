from __future__ import annotations

from ndd_corpus.pmc.id_mapping import CachingConverter, map_pmcids


class FakeConverter:
    def __init__(self) -> None:
        self.batches: list[tuple[str, ...]] = []

    def convert(self, pmids: tuple[str, ...]) -> list[dict[str, str]]:
        self.batches.append(pmids)
        return [
            {"pmid": pmid, "pmcid": f"PMC{pmid}", "doi": f"10.test/{pmid}"}
            for pmid in pmids
            if pmid != "3"
        ]


def test_mapping_prefers_pubmed_metadata_then_batches_remaining_ids() -> None:
    articles = [
        {"pmid": "1", "pmcid_if_present": "PMC100", "doi": "10.test/existing"},
        {"pmid": "2", "pmcid_if_present": None, "doi": None},
        {"pmid": "3", "pmcid_if_present": None, "doi": None},
    ]
    converter = FakeConverter()

    rows = map_pmcids(articles, converter=converter, batch_size=2)

    assert converter.batches == [("2", "3")]
    assert rows == [
        {
            "pmid": "1",
            "pmcid": "PMC100",
            "doi": "10.test/existing",
            "mapping_source": "pubmed",
            "mapping_status": "mapped",
        },
        {
            "pmid": "2",
            "pmcid": "PMC2",
            "doi": "10.test/2",
            "mapping_source": "pmc_id_converter",
            "mapping_status": "mapped",
        },
        {
            "pmid": "3",
            "pmcid": None,
            "doi": None,
            "mapping_source": "pmc_id_converter",
            "mapping_status": "not_in_pmc",
        },
    ]


def test_converter_errors_are_failed_not_unmapped() -> None:
    class ErrorConverter:
        def convert(self, _pmids: tuple[str, ...]) -> list[dict[str, str]]:
            return [{"pmid": "4", "status": "error"}]

    rows = map_pmcids(
        [{"pmid": "4", "pmcid_if_present": None, "doi": None}],
        converter=ErrorConverter(),
    )

    assert rows[0]["mapping_status"] == "failed"


def test_converter_cache_resumes_completed_batches(tmp_path) -> None:
    source = FakeConverter()

    first = CachingConverter(source, tmp_path).convert(("2", "3"))
    second = CachingConverter(source, tmp_path).convert(("2", "3"))

    assert first == second
    assert source.batches == [("2", "3")]
