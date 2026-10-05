from __future__ import annotations

from ndd_corpus.pubmed.query_builder import build_disease_query, build_generic_query


def test_disease_query_escapes_quotes_and_combines_terms() -> None:
    result = build_disease_query(
        "MONDO:0000002", ['Alpha "quoted" syndrome', "Beta syndrome"]
    )

    assert result.query == (
        '("Alpha \\"quoted\\" syndrome"[Title/Abstract] OR '
        '"Beta syndrome"[Title/Abstract])'
    )
    assert result.terms == ('Alpha "quoted" syndrome', "Beta syndrome")


def test_query_id_is_stable_across_input_order_and_duplicates() -> None:
    first = build_disease_query("MONDO:0000002", ["Beta", "Alpha", "alpha"])
    second = build_disease_query("MONDO:0000002", ["Alpha", "Beta"])

    assert first.query_id == second.query_id
    assert first.terms == ("Alpha", "Beta")


def test_generic_query_contains_mesh_and_title_abstract_terms() -> None:
    query = build_generic_query()

    assert '"Neurodevelopmental Disorders"[MeSH Terms]' in query.query
    assert '"global developmental delay"[Title/Abstract]' in query.query
    assert query.branch == "broad_ndd"

