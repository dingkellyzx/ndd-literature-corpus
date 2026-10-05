from __future__ import annotations

from ndd_corpus.diseases.build_catalog import build_catalog, build_search_terms
from ndd_corpus.diseases.mondo import MondoGraph, MondoNode
from ndd_corpus.diseases.orphanet import OrphaRecord, parse_orphadata


def _mondo_graph() -> MondoGraph:
    root = MondoNode(
        mondo_id="MONDO:0700092",
        name="neurodevelopmental disorder",
        exact_synonyms=(),
        narrow_synonyms=(),
        related_synonyms=(),
        xrefs=(),
        parents=(),
        is_rare=False,
    )
    child = MondoNode(
        mondo_id="MONDO:0000002",
        name="Pitt-Hopkins syndrome",
        exact_synonyms=("Pitt Hopkins syndrome", "PTHS", "developmental disorder"),
        narrow_synonyms=("Pitt-Hopkins-like syndrome",),
        related_synonyms=("developmental disorder",),
        xrefs=("Orphanet:2896", "OMIM:610954"),
        parents=("MONDO:0700092",),
        is_rare=True,
    )
    unmatched = MondoNode(
        mondo_id="MONDO:0000003",
        name="Different syndrome",
        exact_synonyms=(),
        narrow_synonyms=(),
        related_synonyms=(),
        xrefs=(),
        parents=("MONDO:0700092",),
        is_rare=True,
    )
    return MondoGraph(
        nodes={node.mondo_id: node for node in (root, child, unmatched)},
        children={"MONDO:0700092": {"MONDO:0000002", "MONDO:0000003"}},
    )


def test_parse_orphadata_extracts_names_synonyms_and_cross_references() -> None:
    payload = {
        "JDBOR": {
            "DisorderList": {
                "Disorder": [
                    {
                        "OrphaCode": "2896",
                        "Name": {"#text": "Pitt-Hopkins syndrome"},
                        "SynonymList": {"Synonym": ["PTHS syndrome"]},
                        "ExternalReferenceList": {
                            "ExternalReference": [
                                {"Source": "MONDO", "Reference": "0000002"},
                                {"Source": "OMIM", "Reference": "610954"},
                                {"Source": "MeSH", "Reference": "D000001"},
                            ]
                        },
                    }
                ]
            }
        }
    }

    records = parse_orphadata(payload)

    assert records == [
        OrphaRecord(
            orpha_id="ORPHA:2896",
            preferred_name="Pitt-Hopkins syndrome",
            synonyms=("PTHS syndrome",),
            mondo_ids=("MONDO:0000002",),
            omim_ids=("OMIM:610954",),
            mesh_ids=("MeSH:D000001",),
        )
    ]


def test_catalog_uses_exact_cross_reference_and_rare_filter() -> None:
    orpha = OrphaRecord(
        orpha_id="ORPHA:2896",
        preferred_name="Pitt-Hopkins syndrome",
        synonyms=("PTHS syndrome",),
        mondo_ids=("MONDO:0000002",),
        omim_ids=("OMIM:610954",),
        mesh_ids=("MeSH:D000001",),
    )

    complete, catalog = build_catalog(
        _mondo_graph(),
        root="MONDO:0700092",
        rare_only=True,
        orphanet_records=[orpha],
    )

    assert {row["mondo_id"] for row in complete} == {
        "MONDO:0700092",
        "MONDO:0000002",
        "MONDO:0000003",
    }
    assert [row["mondo_id"] for row in catalog] == ["MONDO:0000002", "MONDO:0000003"]
    assert catalog[0]["orpha_id"] == "ORPHA:2896"
    assert catalog[0]["omim_ids"] == ["OMIM:610954"]
    assert catalog[1]["orpha_id"] is None


def test_search_terms_keep_exclusions_for_audit() -> None:
    _complete, catalog = build_catalog(
        _mondo_graph(), root="MONDO:0700092", rare_only=True, orphanet_records=[]
    )

    terms = build_search_terms(catalog)
    by_term = {row["term"]: row for row in terms}

    assert by_term["Pitt-Hopkins syndrome"]["use_for_pubmed"] is True
    assert by_term["PTHS"]["use_for_pubmed"] is True
    assert by_term["developmental disorder"]["use_for_pubmed"] is False
    assert by_term["developmental disorder"]["exclusion_reason"] == "generic"
