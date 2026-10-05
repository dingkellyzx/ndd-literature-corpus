# Neurodevelopmental Disease Literature Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and verify a resumable Python pipeline for MONDO/Orphadata, PubMed, and PMC literature acquisition without launching the full download.

**Architecture:** Focused `src/ndd_corpus` modules expose testable functions; thin scripts compose them into stages. SQLite records transactional work state while Parquet/XML/JSON files are the portable outputs.

**Tech Stack:** Python 3.12, httpx, pydantic-settings, PyYAML, lxml, pyarrow, tenacity, pytest, respx, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-05-ndd-literature-corpus-design.md`

## Global Constraints

- Never commit downloaded literature or credentials.
- Never log `NCBI_API_KEY`; require `NCBI_EMAIL` only for live NCBI calls.
- Use official MONDO/Orphadata bulk products, NCBI E-utilities/ID Converter, and the current PMC AWS Article Dataset.
- Persist raw XML before parsing and retain retrieval/license provenance.
- Do not implement phenotype, gene, variant, relation, embedding, or knowledge-graph extraction.
- Use deterministic ordering, atomic writes, checksums, and restart-safe stages.

## Review Focus

- Malformed or evolving ontology/Orphadata payloads fail with source-specific diagnostics.
- ESearch boundary partitions neither truncate nor double-count records.
- Interrupted downloads never become completed artifacts.
- Multiple PMC versions are selected from metadata, never version number alone.
- Secrets and signed query values are absent from logs and persisted provenance.

---

### Task 1: Foundation, configuration, and checkpointing

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `configs/default.yaml`
- Create: `src/ndd_corpus/config.py`, `src/ndd_corpus/utils/{http,retry,checkpoint,logging}.py`
- Test: `tests/auto-tests/test_config.py`, `tests/auto-tests/test_resume.py`

**Interfaces:**
- Produces: `Settings.load(path)`, `NcbiClient`, `CheckpointStore`, atomic download/checksum helpers.

- [ ] Write failing tests for path resolution, credential validation, retry-safe atomic writes, interrupted-state reset, and completed-file skipping.
- [ ] Run the focused tests and confirm missing imports/behavior fail.
- [ ] Implement the minimum foundation interfaces and default configuration.
- [ ] Run the focused tests and the full suite; commit.

### Task 2: MONDO, Orphadata, and search terms

**Files:**
- Create: `src/ndd_corpus/diseases/{mondo,orphanet,build_catalog}.py`
- Create: `scripts/download_reference_data.py`, `scripts/build_disease_catalog.py`
- Test: `tests/auto-tests/test_mondo.py`, `tests/auto-tests/test_disease_catalog.py`

**Interfaces:**
- Consumes: settings, HTTP client, checkpoint/checksum helpers.
- Produces: `parse_mondo`, `descendants`, `parse_orphadata`, `build_catalog`, `build_search_terms` and required Parquet outputs.

- [ ] Write failing fixture tests for root traversal, cycles, obsolete terms, explicit rare membership, exact Orphanet enrichment, and exclusion reasons.
- [ ] Run focused tests and confirm failures.
- [ ] Implement reference download/parsing and deterministic catalog/search-term materialization.
- [ ] Run focused tests and the full suite; commit.

### Task 3: PubMed search, fetch, and parsing

**Files:**
- Create: `src/ndd_corpus/pubmed/{query_builder,search,fetch,parser}.py`
- Create: `scripts/search_pubmed.py`, `scripts/download_pubmed.py`
- Test: `tests/auto-tests/test_query_builder.py`, `test_pubmed_search.py`, `test_pubmed_parser.py`

**Interfaces:**
- Consumes: settings, `NcbiClient`, checkpoint store, search terms.
- Produces: `build_disease_query`, `partition_search`, `fetch_batches`, `parse_pubmed_xml` and required search/article manifests.

- [ ] Write failing tests for escaping, query provenance, recursive partitioning/count reconciliation, deterministic batches, structured abstracts, missing abstracts, IDs, and retractions.
- [ ] Run focused tests and confirm failures.
- [ ] Implement search/fetch/parser modules and thin scripts.
- [ ] Run focused tests and the full suite; commit.

### Task 4: PMCID mapping and PMC Article Dataset retrieval

**Files:**
- Create: `src/ndd_corpus/pmc/{id_mapping,inventory,downloader,parser}.py`
- Create: `scripts/map_pmc.py`, `scripts/download_pmc.py`
- Test: `tests/auto-tests/test_pmc_mapping.py`, `test_pmc_inventory.py`, `test_pmc_parser.py`

**Interfaces:**
- Consumes: PubMed articles, HTTP/checkpoint helpers.
- Produces: `map_pmcids`, inventory discovery/filtering, `select_version`, XML downloads, `parse_jats` and required PMC tables.

- [ ] Write failing tests for mapped/unmapped batches, inventory manifests, absent `.1`, manuscript/published/retracted candidates, MD5 verification, JATS sections, and resume.
- [ ] Run focused tests and confirm failures.
- [ ] Implement mapping, inventory, version selection, downloads, parsing, and scripts.
- [ ] Run focused tests and the full suite; commit.

### Task 5: Corpus assembly, validation, reporting, and operator workflow

**Files:**
- Create: `src/ndd_corpus/corpus/{merge,deduplicate,validate}.py`
- Create: `scripts/build_corpus.py`, `scripts/summarize.py`, `scripts/run_all.sh`
- Create: `README.md`, fixture files, package initializers.
- Test: `tests/auto-tests/test_deduplication.py`, `test_validation.py`, `test_pipeline.py`

**Interfaces:**
- Consumes: all stage outputs.
- Produces: canonical articles, sections, disease retrieval provenance, deduplication log, validation report, and summary JSON/text.

- [ ] Write failing tests for identifier-priority merges, recorded title fallbacks, fatal/warning validations, summary counts, and a fixture-backed end-to-end resume run.
- [ ] Run focused tests and confirm failures.
- [ ] Implement assembly/validation/reporting, full script orchestration, and local `tmux` full-run instructions.
- [ ] Run pytest, ruff, mypy, build/install smoke checks, and the offline debug workflow; commit.

