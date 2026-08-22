#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYSIS_ROOT="$ROOT/services/analysis"
VENV="${BIOSTAT_ANALYSIS_VENV:-$ANALYSIS_ROOT/.venv}"
PYTHON="$VENV/bin/python"
BOOTSTRAP_PYTHON="${BIOSTAT_BOOTSTRAP_PYTHON:-python3}"
LOCK_FILE="$ANALYSIS_ROOT/requirements.lock"
STAMP="$VENV/.biostat-requirements.sha256"
LOCK_HASH="$(shasum -a 256 "$LOCK_FILE" | awk '{print $1}')"

if ! test -x "$PYTHON"; then
  "$BOOTSTRAP_PYTHON" -m venv "$VENV"
fi

if ! test -f "$STAMP" || test "$(<"$STAMP")" != "$LOCK_HASH"; then
  PIP_NO_CACHE_DIR=1 "$PYTHON" -m pip install --disable-pip-version-check --no-input --requirement "$LOCK_FILE" --timeout 30 --retries 1
  PIP_NO_CACHE_DIR=1 "$PYTHON" -m pip install --disable-pip-version-check --no-input --no-deps -e "$ANALYSIS_ROOT" --no-build-isolation
  printf '%s\n' "$LOCK_HASH" > "$STAMP"
fi
