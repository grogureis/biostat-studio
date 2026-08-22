#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYSIS_ROOT="$ROOT/services/analysis"
VENV="${BIOSTAT_ANALYSIS_VENV:-$ANALYSIS_ROOT/.venv-py312}"
PYTHON="$VENV/bin/python"
BOOTSTRAP_PYTHON="${BIOSTAT_BOOTSTRAP_PYTHON:-python3.12}"
LOCK_FILE="$ANALYSIS_ROOT/requirements.lock"
STAMP="$VENV/.biostat-requirements.sha256"
LOCK_HASH="$(shasum -a 256 "$LOCK_FILE" | awk '{print $1}')"
PACKAGE_HASH="$({
  shasum -a 256 "$ANALYSIS_ROOT/pyproject.toml"
  find "$ANALYSIS_ROOT/biostat_service" -type f -name '*.py' -exec shasum -a 256 {} +
} | LC_ALL=C sort | shasum -a 256 | awk '{print $1}')"
BOOTSTRAP_VERSION="$("$BOOTSTRAP_PYTHON" -c 'import platform; print(platform.python_version())')"

if [[ "$BOOTSTRAP_VERSION" != 3.12.* ]]; then
  printf 'BioStat Studio requires Python 3.12; found %s.\n' "$BOOTSTRAP_VERSION" >&2
  exit 2
fi

if ! test -x "$PYTHON"; then
  "$BOOTSTRAP_PYTHON" -m venv "$VENV"
fi

VENV_VERSION="$("$PYTHON" -c 'import platform; print(platform.python_version())')"
if [[ "$VENV_VERSION" != 3.12.* ]]; then
  printf 'BioStat Studio analysis environment must use Python 3.12; found %s.\n' "$VENV_VERSION" >&2
  exit 2
fi
STAMP_VALUE="$LOCK_HASH:package-$PACKAGE_HASH:python-$VENV_VERSION"

if ! test -f "$STAMP" || test "$(<"$STAMP")" != "$STAMP_VALUE"; then
  PIP_NO_CACHE_DIR=1 "$PYTHON" -m pip install --disable-pip-version-check --no-input --requirement "$LOCK_FILE" --timeout 30 --retries 1
  PIP_NO_CACHE_DIR=1 "$PYTHON" -m pip install --disable-pip-version-check --no-input --no-deps --force-reinstall "$ANALYSIS_ROOT" --no-build-isolation
  "$PYTHON" -c 'import biostat_service'
  printf '%s\n' "$STAMP_VALUE" > "$STAMP"
fi
