from __future__ import annotations

import pytest

from ndd_corpus.diseases.mondo import descendants, parse_mondo


def _node(
    identifier: str,
    label: str,
    *,
    subsets: list[str] | None = None,
    deprecated: bool = False,
) -> dict[str, object]:
    return {
        "id": f"http://purl.obolibrary.org/obo/{identifier.replace(':', '_')}",
        "lbl": label,
        "meta": {"subsets": subsets or [], "deprecated": deprecated},
    }


def _fixture(*, cycle: bool = False) -> dict[str, object]:
    root = "http://purl.obolibrary.org/obo/MONDO_0700092"
    child = "http://purl.obolibrary.org/obo/MONDO_0000002"
    edges = [{"sub": child, "pred": "is_a", "obj": root}]
    if cycle:
        edges.append({"sub": root, "pred": "is_a", "obj": child})
    return {
        "graphs": [
            {
                "nodes": [
                    _node("MONDO:0700092", "neurodevelopmental disorder"),
                    _node("MONDO:0000002", "example syndrome"),
                    _node("MONDO:0000003", "obsolete syndrome", deprecated=True),
                ],
                "edges": edges
                + [
                    {
                        "sub": "http://purl.obolibrary.org/obo/MONDO_0000003",
                        "pred": "is_a",
                        "obj": root,
                    }
                ],
            }
        ]
    }


def test_descendant_traversal_keeps_root_and_excludes_obsolete_terms() -> None:
    graph = parse_mondo(_fixture())

    result = descendants(graph, "MONDO:0700092")

    assert [node.mondo_id for node in result] == ["MONDO:0000002", "MONDO:0700092"]


def test_missing_root_fails_with_identifier() -> None:
    graph = parse_mondo(_fixture())

    with pytest.raises(ValueError, match="MONDO:9999999"):
        descendants(graph, "MONDO:9999999")


def test_cycle_in_reachable_hierarchy_fails() -> None:
    graph = parse_mondo(_fixture(cycle=True))

    with pytest.raises(ValueError, match="cycle"):
        descendants(graph, "MONDO:0700092")


def test_rare_membership_requires_explicit_rare_subset() -> None:
    payload = {
        "graphs": [
            {
                "nodes": [
                    _node("MONDO:0000001", "context parent"),
                    _node(
                        "MONDO:0000002",
                        "rare syndrome",
                        subsets=["http://purl.obolibrary.org/obo/mondo#rare"],
                    ),
                ],
                "edges": [],
            }
        ]
    }

    graph = parse_mondo(payload)

    assert graph.nodes["MONDO:0000001"].is_rare is False
    assert graph.nodes["MONDO:0000002"].is_rare is True

