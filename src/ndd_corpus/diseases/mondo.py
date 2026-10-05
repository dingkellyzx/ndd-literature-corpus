from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

RARE_SUBSET = "http://purl.obolibrary.org/obo/mondo#rare"


def _curie(value: str) -> str:
    tail = value.rsplit("/", 1)[-1]
    if tail.startswith("MONDO_"):
        return tail.replace("MONDO_", "MONDO:", 1)
    return value


@dataclass(frozen=True, slots=True)
class MondoNode:
    mondo_id: str
    name: str
    exact_synonyms: tuple[str, ...]
    narrow_synonyms: tuple[str, ...]
    related_synonyms: tuple[str, ...]
    xrefs: tuple[str, ...]
    parents: tuple[str, ...]
    is_rare: bool
    obsolete: bool = False


@dataclass(frozen=True, slots=True)
class MondoGraph:
    nodes: dict[str, MondoNode]
    children: dict[str, set[str]]


def _values(items: Any, key: str = "val") -> tuple[str, ...]:
    if not isinstance(items, list):
        return ()
    values = []
    for item in items:
        value = item.get(key) if isinstance(item, dict) else item
        if value:
            values.append(str(value).strip())
    return tuple(sorted(set(values), key=str.casefold))


def parse_mondo(payload: dict[str, Any]) -> MondoGraph:
    graphs = payload.get("graphs")
    if not isinstance(graphs, list) or not graphs:
        raise ValueError("MONDO payload has no OBO graph")
    graph = graphs[0]
    raw_nodes = graph.get("nodes", [])
    raw_edges = graph.get("edges", [])
    parent_map: dict[str, set[str]] = {}
    children: dict[str, set[str]] = {}
    for edge in raw_edges:
        if not isinstance(edge, dict) or edge.get("pred") not in {
            "is_a",
            "http://www.w3.org/2000/01/rdf-schema#subClassOf",
        }:
            continue
        child = _curie(str(edge.get("sub", "")))
        parent = _curie(str(edge.get("obj", "")))
        if child.startswith("MONDO:") and parent.startswith("MONDO:"):
            parent_map.setdefault(child, set()).add(parent)
            children.setdefault(parent, set()).add(child)
    nodes: dict[str, MondoNode] = {}
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            continue
        mondo_id = _curie(str(raw_node.get("id", "")))
        if not mondo_id.startswith("MONDO:"):
            continue
        raw_meta = raw_node.get("meta")
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        synonyms: dict[str, list[str]] = {"exact": [], "narrow": [], "related": []}
        for synonym in meta.get("synonyms", []):
            if not isinstance(synonym, dict) or not synonym.get("val"):
                continue
            predicate = str(synonym.get("pred", "")).casefold()
            category = next(
                (kind for kind in synonyms if kind in predicate),
                "related",
            )
            synonyms[category].append(str(synonym["val"]).strip())
        subsets = set(_values(meta.get("subsets"), key="id"))
        if not subsets and isinstance(meta.get("subsets"), list):
            subsets = {str(item) for item in meta["subsets"]}
        obsolete = meta.get("deprecated") in {True, "true", "True"}
        nodes[mondo_id] = MondoNode(
            mondo_id=mondo_id,
            name=str(raw_node.get("lbl") or mondo_id).strip(),
            exact_synonyms=tuple(sorted(set(synonyms["exact"]), key=str.casefold)),
            narrow_synonyms=tuple(sorted(set(synonyms["narrow"]), key=str.casefold)),
            related_synonyms=tuple(sorted(set(synonyms["related"]), key=str.casefold)),
            xrefs=_values(meta.get("xrefs")),
            parents=tuple(sorted(parent_map.get(mondo_id, set()))),
            is_rare=RARE_SUBSET in subsets or any(value.endswith("#rare") for value in subsets),
            obsolete=obsolete,
        )
    return MondoGraph(nodes=nodes, children=children)


def merge_rare_membership(full: MondoGraph, rare: MondoGraph) -> MondoGraph:
    rare_ids = {mondo_id for mondo_id, node in rare.nodes.items() if node.is_rare}
    nodes = {
        mondo_id: replace(node, is_rare=node.is_rare or mondo_id in rare_ids)
        for mondo_id, node in full.nodes.items()
    }
    return MondoGraph(nodes=nodes, children=full.children)


def descendants(graph: MondoGraph, root: str) -> list[MondoNode]:
    if root not in graph.nodes:
        raise ValueError(f"MONDO root not found: {root}")
    visited: set[str] = set()
    active: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in active:
            raise ValueError(f"cycle detected in MONDO hierarchy at {identifier}")
        if identifier in visited:
            return
        active.add(identifier)
        for child in sorted(graph.children.get(identifier, set())):
            visit(child)
        active.remove(identifier)
        visited.add(identifier)

    visit(root)
    return sorted(
        (graph.nodes[identifier] for identifier in visited if not graph.nodes[identifier].obsolete),
        key=lambda node: node.mondo_id,
    )
