#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p data/logs
RUN_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="data/logs/run_${RUN_TIMESTAMP}.log"
PYTHON_BIN="${PYTHON_BIN:-python}"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[pipeline] started ${RUN_TIMESTAMP}"
"$PYTHON_BIN" scripts/download_reference_data.py
"$PYTHON_BIN" scripts/build_disease_catalog.py
"$PYTHON_BIN" scripts/search_pubmed.py
"$PYTHON_BIN" scripts/download_pubmed.py
"$PYTHON_BIN" scripts/map_pmc.py
"$PYTHON_BIN" scripts/download_pmc.py
"$PYTHON_BIN" scripts/build_corpus.py
"$PYTHON_BIN" scripts/screen_relevance.py
"$PYTHON_BIN" scripts/summarize.py
echo "[pipeline] complete; log=$LOG_FILE"
