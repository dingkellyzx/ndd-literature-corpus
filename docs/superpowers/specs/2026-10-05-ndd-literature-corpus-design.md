# Neurodevelopmental Disease Literature Corpus Design

## Outcome

Build a standalone Python 3.12 repository that defines a MONDO-based rare
neurodevelopmental disease set and retrieves an auditable, resumable PubMed and
PMC literature corpus. This delivery includes code, automated tests, and a
capped live debug workflow. It does not launch the full corpus download and it
does not perform downstream NLP.

## Architecture

The pipeline is a sequence of independently resumable stages:

1. Download and checksum MONDO and Orphadata reference files.
2. Build the complete MONDO NDD descendant table, the configured rare catalog,
   and an auditable search-term table.
3. Run broad and per-disease PubMed searches with recursively partitioned date
   ranges and exact count reconciliation.
4. Fetch and parse raw PubMed XML in deterministic batches.
5. Map PMID to PMCID, match PMC Article Dataset inventory entries, select an
   article version, and download and parse JATS XML.
6. Merge, deduplicate, validate, and summarize the canonical corpus.

Thin scripts call focused functions in `src/ndd_corpus`. SQLite is the
transactional operational ledger; required scientific outputs and exported
manifests remain Parquet, JSON, XML, and text. Downloads use temporary files,
checksum verification, and atomic rename. A completed artifact is reused only
when its file and checksum are valid.

## Configuration and security

`configs/default.yaml` is the single user-facing configuration file. Relative
paths resolve from the repository root. `NCBI_EMAIL` is required for live NCBI
operations and `NCBI_API_KEY` is optional. A local `.env` is ignored by Git;
credentials are never printed, persisted in provenance, or placed in URLs that
are logged.

## Disease catalog

The reference stage downloads the full stable MONDO JSON release and the MONDO
rare-subset JSON release. Descendants are determined only from `is_a` edges
below `MONDO:0700092`; obsolete nodes are excluded from canonical output but
retained in diagnostics. Rare membership requires an explicit MONDO `rare`
subset annotation rather than mere presence in the rare-subset graph, whose
parent nodes are included for context.

Orphadata is bulk-downloaded and used only to enrich diseases already selected
by MONDO. Exact MONDO/ORPHA cross-references are accepted; fuzzy or name-only
alignment is out of scope. Search terms retain enabled and excluded terms with
explicit exclusion reasons.

## PubMed retrieval

The broad and disease-specific branches remain independent. Each query has a
stable content-derived ID and preserves its exact text and constituent terms.
Searches count first, then split year, month, and day partitions until each
leaf is below PubMed's 10,000-result ESearch ceiling. A leaf is committed only
when its reported count equals the number of unique PMIDs retrieved.

Because an OR expression cannot identify which synonym caused a match,
`matched_search_term` is nullable and `query_terms` preserves the honest query
provenance. PubMed XML is stored before parsing. Articles without abstracts are
valid and receive `has_abstract=false`.

## PMC retrieval

PMCID mapping uses PubMed article identifiers first and the official PMC ID
Converter for remaining PMIDs in batches of at most 200. `not_in_pmc` is a
successful terminal mapping state.

Full text comes only from the current `pmc-oa-opendata` AWS Article Dataset.
The pipeline discovers and caches the latest daily inventory, downloads the
referenced JSON metadata objects, selects non-retracted published versions over
manuscripts where possible, records all candidates, and follows metadata
`xml_url` values. It never guesses `.1`, scrapes HTML, or uses removed legacy
FTP layouts. License metadata remains attached to every full-text record.

## Corpus and validation

Canonical identity prefers PMID, then PMCID, then normalized DOI. Normalized
title is only a recorded fallback when identifiers are absent. PubMed is the
authority for citation metadata and PMC for full text, JATS sections, and
licenses. Large body text is stored in `article_sections.parquet` rather than
the main article table.

Required validation failures include incomplete ESearch partitions, duplicate
canonical PMIDs, conflicting PMID/PMCID mappings, invalid identifiers, corrupt
XML, missing completed artifacts, and empty disease/search/article outputs.
Expected coverage gaps such as absent abstracts or PMC mappings are warnings.

## Testing and execution boundary

Unit and fixture-backed integration tests cover ontology traversal, query
escaping and partitioning, XML parsing, version selection, deduplication,
validation, and restart behavior. A capped debug configuration exercises the
same stage graph with 10 diseases, 100 PubMed records, and 20 PMC records. This
delivery will not run the uncapped full download; the README will provide exact
`tmux` launch, monitoring, resume, and validation instructions for the local
machine.

