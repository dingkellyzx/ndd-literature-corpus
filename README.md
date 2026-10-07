# NDD Literature Corpus

A reproducible, restartable Python pipeline for acquiring a high-recall
neurodevelopmental disease literature corpus from MONDO, Orphanet, PubMed, and
the PMC Article Dataset. It builds disease/search-term tables, retains raw XML
and retrieval provenance, and produces canonical Parquet article and section
tables. An optional post-retrieval relevance-screening stage creates a
conservative downstream extraction corpus without narrowing acquisition.

This repository performs high-recall literature acquisition and optional
paper-level relevance screening. It does not extract HPO terms, phenotypes,
onset, genes, variants, relations, embeddings, or knowledge graphs. Retrieval
provenance is never altered by relevance screening.

## Data sources and terms

- [MONDO](https://mondo.monarchinitiative.org/) supplies the authoritative NDD
  hierarchy and rare-disease annotations under CC BY 4.0.
- [Orphadata](https://www.orphadata.com/) enriches MONDO diseases with ORPHA
  names and mappings under CC BY 4.0.
- [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) supplies
  citation metadata. Not every citation contains an abstract.
- [PMC Article Datasets on AWS](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/)
  supplies reusable JATS XML and per-version license metadata. Not every PubMed
  article is in PMC, and not every PMC web article is distributed in the
  reusable Article Dataset.

Retain PMC license fields in every downstream dataset. Review the source terms
before redistributing data. Cite MONDO, Orphanet, PubMed, and the PMC Article
Dataset in resulting research products.

## Installation

Python 3.12 or newer is required.

```bash
cd /home/dingzx/Documents/ChatGPT/Code/ndd-literature-corpus
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Edit `.env` and set your real values:

```dotenv
NCBI_EMAIL=you@example.org
NCBI_API_KEY=
```

`NCBI_EMAIL` is required for live NCBI requests. `NCBI_API_KEY` is optional.
The `.env` file, downloaded data, logs, and checkpoint database are ignored by
Git. Credentials are not written into provenance tables or logs.

Relevance screening uses the OpenAI-compatible local Ollama endpoint configured
under `relevance` in `configs/default.yaml`. The default is
`http://127.0.0.1:11434/v1` with `qwen3:14b`; install Ollama and make that model
available before an enabled run. Qwen3's thinking phase is disabled by
default (`relevance.think: false`, sent as `reasoning_effort: "none"`); set
`think: true` to restore the model default. No OpenAI package or API key is
used. Set `relevance.enabled: false` to retain every article through the same
downstream file interface.

## Verify the code

```bash
source .venv/bin/activate
pytest -q
ruff check src scripts tests
mypy src/ndd_corpus
python -m build
```

The fixture-backed integration test exercises disease construction, PubMed and
JATS parsing, canonical merging, provenance, and validation without network
access:

```bash
pytest tests/auto-tests/test_pipeline.py -q
```

## Debug run

`configs/default.yaml` ships with `debug.enabled: true`. The debug caps are 10
diseases, approximately 100 reconciled PubMed results, and 20 PMC articles.
Every processed ESearch leaf still satisfies reported-count equals retrieved
unique-PMID count. Run:

```bash
source .venv/bin/activate
bash scripts/run_all.sh
```

Before any full run, inspect:

```bash
python - <<'PY'
import random
import pyarrow.parquet as pq
for path, count in [
    ('data/processed/disease_catalog.parquet', 10),
    ('data/interim/pubmed/articles.parquet', 20),
    ('data/interim/pmc/articles.parquet', 10),
]:
    rows = pq.read_table(path).to_pylist()
    print(path, random.sample(rows, min(count, len(rows))))
PY
cat data/processed/validation_report.json
cat data/processed/corpus_summary.txt
```

## Full corpus download on this machine

Do this only after tests and the debug run pass and the sampled records look
correct.

1. Edit `configs/default.yaml` and change `debug.enabled` to `false`.
2. Start a persistent terminal session:

   ```bash
   cd /home/dingzx/Documents/ChatGPT/Code/ndd-literature-corpus
   tmux new-session -s ndd-corpus
   source .venv/bin/activate
   bash scripts/run_all.sh
   ```

3. Detach with `Ctrl-b`, then `d`.
4. Reattach later with `tmux attach-session -t ndd-corpus`.
5. Follow the current log from another terminal:

   ```bash
   tail -f "$(ls -1t data/logs/run_*.log | head -1)"
   ```

If the process or machine stops, reattach or start a new `tmux` session and run
`bash scripts/run_all.sh` again. Valid PubMed search-cache leaves, PubMed XML
batches, and PMC XML files are reused; interrupted `running` entries reset to
`pending`; failed entries retry. Do not delete `data/interim/checkpoints.sqlite`
or the search cache when resuming.

To retain the default debug configuration in Git, make the full-run change
locally and do not commit it. After the run, restore `debug.enabled: true`
manually.

## Individual stages

```bash
python scripts/download_reference_data.py
python scripts/build_disease_catalog.py
python scripts/search_pubmed.py
python scripts/download_pubmed.py
python scripts/map_pmc.py
python scripts/download_pmc.py
python scripts/build_corpus.py
python scripts/screen_relevance.py
python scripts/summarize.py
```

Each network stage stores raw inputs before parsing. PubMed and PMC downloads
use atomic writes and checksums. PubMed searches are date-partitioned below the
10,000-result ESearch ceiling and cached per exact query/date leaf.

## Main outputs

- `data/processed/disease_catalog.parquet`
- `data/interim/diseases/search_terms.parquet`
- `data/interim/pubmed/search_results.parquet`
- `data/interim/pubmed/articles.parquet`
- `data/interim/pmc/pmid_pmcid.parquet`
- `data/processed/articles.parquet`
- `data/processed/article_sections.parquet`
- `data/processed/article_disease_retrieval.parquet`
- `data/processed/article_relevance.parquet`
- `data/processed/articles_relevant.parquet`
- `data/processed/article_sections_relevant.parquet`
- `data/processed/article_relevance.csv` (debug convenience copy)
- `data/processed/relevance_debug_report.txt`
- `data/interim/relevance/errors.jsonl` (classifier failures)
- `data/processed/validation_report.json`
- `data/processed/corpus_summary.json`
- `data/processed/corpus_summary.txt`

`articles.parquet` is the complete high-recall acquisition corpus.
`articles_relevant.parquet` is the screened corpus intended for downstream
biomedical extraction; by default it contains `HIGH` and `POSSIBLE` papers.
`article_relevance.parquet` audits every candidate, including `LOW` papers.
The original article, section, and retrieval-provenance tables are never
overwritten by screening.

Successful relevance results are cached per article and complete request
fingerprint under `data/interim/relevance/`. Articles without abstracts are
still classified from their title, MeSH terms, keywords, publication types, and
retrieval provenance, and the prompt prefers `POSSIBLE` when that metadata is
insufficient. Exhausted classifier retries fail open as `POSSIBLE`; those
failures are audited but not cached, so later runs retry them. Review `relevance_debug_report.txt` and a
manual sample of all three classes before changing the first-run prompt.
