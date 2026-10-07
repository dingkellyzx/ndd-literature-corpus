# Paper-Level Relevance Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add conservative, cached paper-level relevance screening after canonical corpus construction without narrowing or mutating retrieval outputs.

**Architecture:** A focused `ndd_corpus.relevance` package detects metadata signals, builds a stable prompt/request fingerprint, calls Ollama through `httpx`, and orchestrates fail-open screening and filtered Parquet outputs. The command-line stage integrates after corpus construction and extends reporting without redefining acquisition metrics.

**Tech Stack:** Python 3.12, Pydantic 2, httpx, PyArrow, pytest/respx, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-07-paper-relevance-screening-design.md`

## Global Constraints

- Retrieval and its three canonical processed outputs remain unchanged.
- Labels are exactly `HIGH`, `POSSIBLE`, and `LOW`; evidence types use only the eight specified values.
- Missing metadata and classifier failures fail open as retained `POSSIBLE`.
- Only successful validated classifications are cached; transient failures are retried on later runs.
- Full PMC text is never included in classifier requests.
- No OpenAI Python dependency; use the existing `httpx` dependency.

## Review Focus

- Null/list-typed PyArrow metadata fields must normalize without crashes or unstable hashes.
- Duplicate and out-of-order provenance rows must yield deterministic complete unique lists.
- Malformed or semantically invalid model JSON must retry and then fail open without caching.
- `keep_labels` including `LOW` must make eligibility and filtered outputs agree.
- Empty article/section inputs must still produce valid, schema-stable output files.

---

### Task 1: Configuration, models, and deterministic signals

**Files:**
- Create: `src/ndd_corpus/relevance/__init__.py`
- Create: `src/ndd_corpus/relevance/models.py`
- Create: `src/ndd_corpus/relevance/signals.py`
- Modify: `src/ndd_corpus/config.py`
- Modify: `configs/default.yaml`
- Test: `tests/auto-tests/test_relevance_signals.py`
- Test: `tests/auto-tests/test_config.py`

**Interfaces:**
- Produces: `RelevanceConfig`, `RelevanceSignals`, `RetrievalProvenance`, `ClassificationResult`, `ArticleRelevanceRecord`, and `detect_relevance_signals(title, abstract)`.

- [ ] Write tests for configuration defaults/validation and every positive/negative signal group, including case/spacing boundaries and empty input.
- [ ] Run the targeted tests and verify they fail because the new types/functions are absent.
- [ ] Implement the models, configuration, and deterministic signal detector.
- [ ] Run targeted tests and the full suite; verify they pass.

### Task 2: Prompt, classifier, retries, and successful-result cache contract

**Files:**
- Create: `src/ndd_corpus/relevance/prompt.py`
- Create: `src/ndd_corpus/relevance/classifier.py`
- Test: `tests/auto-tests/test_relevance_classifier.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces: canonical prompt/request builders, `prompt_sha256`, `request_hash`, and `OllamaRelevanceClassifier.classify(...)` returning validated `ClassificationResult` or raising a classifier error after configured retries.

- [ ] Write respx-backed tests for exact endpoint/payload boundaries, the fixed label/evidence schema, HIGH/POSSIBLE/LOW examples, malformed responses, retry counts, and request-hash invalidation inputs.
- [ ] Run the targeted tests and verify expected failures.
- [ ] Implement prompt construction, hashing, HTTP calls, JSON extraction/validation, and retry behavior.
- [ ] Run targeted tests and the full suite; verify they pass.

### Task 3: Screening orchestration and persisted outputs

**Files:**
- Create: `src/ndd_corpus/relevance/screen.py`
- Create: `scripts/screen_relevance.py`
- Test: `tests/auto-tests/test_relevance_screen.py`

**Interfaces:**
- Consumes: Task 1 signal/models and Task 2 classifier/fingerprints.
- Produces: provenance aggregation, per-article cache/error audit, `screen_articles(...)`, relevant article/section filtering, Parquet/CSV writers, and CLI summary counts.

- [ ] Write tests for multiple provenance rows, enabled and disabled modes, missing abstracts, fail-open behavior without failure caching, successful cache reuse, configurable keep labels, exact one-record-per-article, empty data, and section filtering.
- [ ] Run the targeted tests and verify expected failures.
- [ ] Implement the orchestration, stable schemas/writers, cache, error JSONL, and CLI.
- [ ] Run targeted tests and the full suite; verify they pass.

### Task 4: Pipeline integration, summary, documentation, and debug report

**Files:**
- Modify: `scripts/run_all.sh`
- Modify: `scripts/summarize.py`
- Modify: `README.md`
- Modify: `.env.example`
- Test: `tests/auto-tests/test_relevance_screen.py`

**Interfaces:**
- Consumes: Task 3 authoritative outputs.
- Produces: automatic post-build screening, separate relevance summary metrics, documented Ollama operation, and `relevance_debug_report.txt` with class/branch/example/target-PMID sections.

- [ ] Write integration tests that run summary/report generation from controlled Parquet fixtures and assert acquisition counts remain separate from relevance counts.
- [ ] Run the targeted tests and verify expected failures.
- [ ] Integrate the stage, summary/report output, README, and environment documentation.
- [ ] Run targeted tests and the full suite; verify they pass.

### Task 5: Repository verification and debug execution

**Files:**
- Verify all changed files and generated debug outputs.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: fresh verification evidence and a first-run review report without classifier tuning.

- [ ] Run `pytest -q`, `ruff check src scripts tests`, `mypy src/ndd_corpus`, and `python -m build` and resolve failures with RED→GREEN regressions where code changes are required.
- [ ] Run `bash scripts/run_all.sh`; confirm the four required Parquet row counts and immutable high-recall inputs.
- [ ] Inspect/report 20 HIGH, 20 POSSIBLE, and 20 LOW where available, and explicitly report PMIDs 18024065 and 18690540 without tuning the first-run prompt.
