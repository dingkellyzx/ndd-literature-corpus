#!/usr/bin/env python3
from __future__ import annotations

import sys

from ndd_corpus.config import Settings
from ndd_corpus.diseases.build_catalog import (
    build_catalog,
    build_search_terms,
    read_json,
    write_parquet,
)
from ndd_corpus.diseases.mondo import merge_rare_membership, parse_mondo
from ndd_corpus.diseases.orphanet import parse_orphadata


def main() -> int:
    settings = Settings.load()
    full_graph = parse_mondo(
        read_json(settings.paths.raw / "reference/mondo/mondo.json")
    )
    rare_graph = parse_mondo(
        read_json(settings.paths.raw / "reference/mondo/mondo-rare.json")
    )
    graph = merge_rare_membership(full_graph, rare_graph)
    orphanet = []
    if settings.disease_scope.use_orphanet:
        orphanet = parse_orphadata(
            read_json(settings.paths.raw / "reference/orphanet/en_product1.json.tar.gz")
        )
    complete, catalog = build_catalog(
        graph,
        root=settings.disease_scope.mondo_root,
        rare_only=settings.disease_scope.rare_only,
        orphanet_records=orphanet,
    )
    if settings.debug.enabled:
        catalog = catalog[: settings.debug.disease_limit]
    terms = build_search_terms(catalog)
    write_parquet(complete, settings.paths.interim / "diseases/mondo_ndd_descendants.parquet")
    write_parquet(catalog, settings.paths.processed / "disease_catalog.parquet")
    write_parquet(terms, settings.paths.interim / "diseases/search_terms.parquet")
    print(
        f"[diseases] {len(complete)} NDD descendants | "
        f"{sum(bool(row['is_rare']) for row in complete)} rare | {len(terms)} terms"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

