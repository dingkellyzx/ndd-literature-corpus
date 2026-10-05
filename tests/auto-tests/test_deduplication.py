from __future__ import annotations

from ndd_corpus.corpus.deduplicate import deduplicate_records, normalize_title
from ndd_corpus.corpus.merge import merge_corpus


def test_merge_prefers_pubmed_metadata_and_pmc_full_text() -> None:
    pubmed = [
        {
            "pmid": "123",
            "pmcid_if_present": "PMC10",
            "doi": "10.1/example",
            "title": "PubMed title",
            "abstract": "PubMed abstract",
            "publication_year": 2025,
            "journal": "Journal",
            "has_abstract": True,
            "mesh_terms": ["Humans"],
            "keywords": ["example"],
            "publication_types": ["Case Reports"],
            "is_retracted": False,
            "pubmed_raw_file": "batch.xml.gz",
        }
    ]
    pmc = [
        {
            "pmid": "123",
            "pmcid": "PMC10",
            "doi": "10.1/example",
            "title": "PMC title",
            "abstract": "PMC abstract",
            "body": "Full text",
            "pmc_version": 2,
            "pmc_license": "CC BY",
            "is_manuscript": "no",
            "is_retracted": "no",
            "pmc_xml_file": "article.xml.gz",
        }
    ]
    retrieval = [
        {
            "pmid": "123",
            "mondo_id": "MONDO:2",
            "retrieval_branch": "disease",
            "query_id": "q1",
            "query": "query one",
            "matched_search_term": None,
        }
    ]

    result = merge_corpus(pubmed, pmc, retrieval, [])

    article = result.articles[0]
    assert article["article_id"] == "PMID:123"
    assert article["title"] == "PubMed title"
    assert article["abstract"] == "PubMed abstract"
    assert article["abstract_pubmed"] == "PubMed abstract"
    assert article["abstract_pmc"] == "PMC abstract"
    assert article["has_fulltext"] is True
    assert article["pmc_license"] == "CC BY"
    assert article["mondo_ids"] == ["MONDO:2"]


def test_title_fallback_is_normalized_and_logged() -> None:
    assert normalize_title("  A—Rare: Syndrome! ") == "a rare syndrome"
    records = [
        {"title": "A—Rare: Syndrome!", "source": "one"},
        {"title": "A Rare Syndrome", "source": "two"},
    ]

    groups, decisions = deduplicate_records(records)

    assert len(groups) == 1
    assert decisions[0]["match_type"] == "normalized_title"
    assert decisions[0]["requires_review"] is True

