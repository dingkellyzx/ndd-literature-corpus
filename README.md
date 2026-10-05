# NDD Literature Corpus

A reproducible, restartable Python pipeline for acquiring a high-recall
neurodevelopmental disease literature corpus from MONDO, Orphanet, PubMed, and
the PMC Article Dataset. It builds disease/search-term tables, retains raw XML
and retrieval provenance, and produces canonical Parquet article and section
tables.

This repository performs literature acquisition only. It does not extract HPO
terms, phenotypes, onset, genes, variants, relations, embeddings, or knowledge
graphs.

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
- `data/processed/validation_report.json`
- `data/processed/corpus_summary.json`
- `data/processed/corpus_summary.txt`

The retrieval strategy deliberately favors recall and will include irrelevant
papers. Later NLP filtering must remain separate from retrieval provenance.
