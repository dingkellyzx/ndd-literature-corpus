# Paper-Level Relevance Screening Design

## Intent

Add an optional post-retrieval screening stage that keeps PubMed acquisition high-recall and immutable while producing a conservative downstream corpus for NDD disease, genetic, variant, phenotype, natural-history, and onset/progression extraction.

## Architecture

`scripts/screen_relevance.py` runs after `scripts/build_corpus.py`. It reads the canonical article table plus all retrieval-provenance rows, derives deterministic evidence signals, and sends only article metadata—not PMC full text—to an OpenAI-compatible Ollama chat-completions endpoint. Every candidate receives exactly one audited `HIGH`, `POSSIBLE`, or `LOW` record.

The original `articles.parquet`, `article_sections.parquet`, and `article_disease_retrieval.parquet` remain unchanged. Retention is controlled by `relevance.keep_labels`, defaulting to `HIGH` and `POSSIBLE`, and creates `articles_relevant.parquet` plus `article_sections_relevant.parquet`.

## Components

- `models.py`: validated signal, provenance, classifier-result, and audit-record models with the fixed label and evidence vocabularies.
- `signals.py`: case-insensitive phrase detection for the supplied positive and negative focus groups; signals are prompt features only.
- `prompt.py`: versioned system prompt, request construction, canonical prompt SHA-256, and strict JSON schema.
- `classifier.py`: `httpx` Ollama client, retry and response validation, and fail-open result construction.
- `screen.py`: provenance aggregation, request hashing, successful-classification cache, audit/error output, and relevant article/section filtering.
- `scripts/screen_relevance.py`: configuration-driven file orchestration and one-line counts.

## Data and audit behavior

The relevance audit table contains identifiers, label/eligibility, evidence types, a short reason, detected signals, all unique provenance values, and model/prompt/request fingerprints. It does not duplicate abstracts.

Successful classifier responses are cached under `data/interim/relevance/` by `article_id` and `request_hash`. Transient failures are written to a JSONL error audit and fail open as `POSSIBLE`, but are not cached so a later run retries them. Disabled screening emits `POSSIBLE` records for all articles and still creates the stable relevant outputs.

## Failure policy

Missing abstracts never imply `LOW`. Invalid responses, transport errors, and exhausted retries retain the article as `POSSIBLE` with the specified conservative reason. A failure for one article does not abort the batch.

## Outputs

- `data/processed/article_relevance.parquet` (all candidates)
- `data/processed/article_relevance.csv` (debug convenience)
- `data/processed/articles_relevant.parquet` (configured retained labels)
- `data/processed/article_sections_relevant.parquet` (sections joined by `article_id`)
- `data/processed/relevance_debug_report.txt` (class/branch counts, examples, and target-PMID inspection)
- `data/interim/relevance/errors.jsonl` (classifier failures)

## Verification

Tests cover exact signal groups, validated classifier output, retries and fail-open behavior, request-hash invalidation, multiple provenance rows, disabled mode, retained article/section joins, and required representative relevance cases. Repository-wide pytest, Ruff, mypy, and package build must pass. A debug pipeline run must preserve the original corpus and produce the relevance outputs and review report; first-run labels are reported for manual review rather than tuned immediately.
