from __future__ import annotations

from pathlib import Path

from ndd_corpus.corpus.validate import build_summary, validate_corpus


def test_validation_fails_duplicates_invalid_ids_and_search_mismatch(tmp_path: Path) -> None:
    articles = [
        {"pmid": "1", "pmcid": "bad", "has_abstract": False, "has_fulltext": False},
        {"pmid": "1", "pmcid": None, "has_abstract": True, "has_fulltext": False},
    ]
    report = validate_corpus(
        articles=articles,
        search_manifest=[{"reported_result_count": 2, "retrieved_unique_pmids": 1}],
        pmc_mapping=[{"pmid": "1", "pmcid": None, "mapping_status": "not_in_pmc"}],
        pubmed_download_manifest=[
            {"status": "complete", "file_path": str(tmp_path / "missing.xml.gz")}
        ],
        pmc_download_manifest=[],
    )

    codes = {item["code"] for item in report.errors}
    warning_codes = {item["code"] for item in report.warnings}
    assert {"duplicate_pmid", "invalid_pmcid", "search_count_mismatch", "missing_file"} <= codes
    assert {"missing_abstract", "pmid_without_pmcid"} <= warning_codes


def test_summary_reports_core_counts() -> None:
    summary = build_summary(
        disease_catalog=[
            {"mondo_id": "MONDO:1", "is_rare": True, "orpha_id": "ORPHA:1"},
            {"mondo_id": "MONDO:2", "is_rare": True, "orpha_id": None},
        ],
        search_terms=[
            {"use_for_pubmed": True},
            {"use_for_pubmed": False},
        ],
        articles=[
            {
                "pmid": "1",
                "publication_year": 1999,
                "has_abstract": True,
                "has_fulltext": True,
                "mondo_ids": ["MONDO:1"],
            },
            {
                "pmid": "2",
                "publication_year": 2001,
                "has_abstract": False,
                "has_fulltext": False,
                "mondo_ids": ["MONDO:1", "MONDO:2"],
            },
        ],
        pmc_mapping=[
            {"mapping_status": "mapped"},
            {"mapping_status": "not_in_pmc"},
        ],
        pmc_downloads=[{"status": "complete"}],
    )

    assert summary["rare_ndd_diseases"] == 2
    assert summary["diseases_with_orphanet_mappings"] == 1
    assert summary["unique_pubmed_pmids"] == 2
    assert summary["articles_with_abstracts"] == 1
    assert summary["articles_with_full_text"] == 1
    assert summary["publication_year_range"] == [1999, 2001]
    assert summary["articles_per_decade"] == {"1990": 1, "2000": 1}

