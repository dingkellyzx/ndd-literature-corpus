from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

from ndd_corpus.corpus.merge import merge_corpus
from ndd_corpus.corpus.validate import validate_corpus
from ndd_corpus.diseases.build_catalog import build_catalog, build_search_terms, write_parquet
from ndd_corpus.diseases.mondo import parse_mondo
from ndd_corpus.diseases.orphanet import parse_orphadata
from ndd_corpus.pmc.parser import parse_jats
from ndd_corpus.pubmed.parser import parse_pubmed_xml

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_fixture_pipeline_builds_valid_canonical_article(tmp_path: Path) -> None:
    mondo = parse_mondo(json.loads((FIXTURES / "mondo-mini.json").read_text()))
    orphanet = parse_orphadata(json.loads((FIXTURES / "orphanet-mini.json").read_text()))
    _complete, diseases = build_catalog(
        mondo,
        root="MONDO:0700092",
        rare_only=True,
        orphanet_records=orphanet,
    )
    terms = build_search_terms(diseases)
    pubmed = parse_pubmed_xml((FIXTURES / "pubmed-mini.xml").read_bytes())
    pmc, sections = parse_jats((FIXTURES / "jats-mini.xml").read_bytes())
    pmc.update(
        {
            "pmc_version": 1,
            "pmc_license": "CC BY",
            "is_manuscript": "no",
            "is_retracted": "no",
            "pmc_xml_file": "fixture.xml.gz",
        }
    )
    retrieval = [
        {
            "pmid": "123",
            "mondo_id": "MONDO:0000002",
            "retrieval_branch": "disease",
            "query_id": "fixture-query",
            "query": "fixture",
            "matched_search_term": None,
        }
    ]

    corpus = merge_corpus(pubmed, [pmc], retrieval, sections)
    report = validate_corpus(
        articles=corpus.articles,
        search_manifest=[{"reported_result_count": 1, "retrieved_unique_pmids": 1}],
        pmc_mapping=[{"pmid": "123", "pmcid": "PMC10", "mapping_status": "mapped"}],
        pubmed_download_manifest=[],
        pmc_download_manifest=[],
    )

    assert len(diseases) == 1
    assert any(row["use_for_pubmed"] for row in terms)
    assert corpus.articles[0]["has_fulltext"] is True
    assert corpus.sections[0]["article_id"] == "PMID:123"
    assert report.errors == []

    article_path = write_parquet(corpus.articles, tmp_path / "articles.parquet")
    section_path = write_parquet(corpus.sections, tmp_path / "sections.parquet")
    assert pq.read_table(article_path).num_rows == 1
    assert pq.read_table(section_path).num_rows == 1
