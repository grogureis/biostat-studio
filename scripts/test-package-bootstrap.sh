#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d /private/tmp/biostat-bootstrap-test.XXXXXX)"
trap 'rm -rf "$TEST_ROOT"' EXIT

FAKE_PYTHON="$TEST_ROOT/python3"
VENV="$TEST_ROOT/analysis-venv"
LOG="$TEST_ROOT/bootstrap.log"

cp "$ROOT/scripts/tests/fixtures/bootstrap-python" "$FAKE_PYTHON"
chmod +x "$FAKE_PYTHON"

OLD_VENV="$TEST_ROOT/old-analysis-venv"
set +e
BIOSTAT_FAKE_VERSION="3.9.99" \
BIOSTAT_BOOTSTRAP_LOG="$LOG" \
BIOSTAT_BOOTSTRAP_PYTHON="$FAKE_PYTHON" \
BIOSTAT_ANALYSIS_VENV="$OLD_VENV" \
bash "$ROOT/scripts/bootstrap-analysis-venv.sh"
old_status=$?
set -e
test "$old_status" -ne 0
test ! -e "$OLD_VENV"

BIOSTAT_BOOTSTRAP_LOG="$LOG" \
BIOSTAT_BOOTSTRAP_PYTHON="$FAKE_PYTHON" \
BIOSTAT_ANALYSIS_VENV="$VENV" \
bash "$ROOT/scripts/bootstrap-analysis-venv.sh"

test -f "$VENV/.biostat-requirements.sha256"
grep -Fqx "venv $VENV" "$LOG"
grep -Fq "pip -m pip install --disable-pip-version-check --no-input --requirement $ROOT/services/analysis/requirements.lock" "$LOG"
grep -Fq "pip -m pip install --disable-pip-version-check --no-input --no-deps -e $ROOT/services/analysis --no-build-isolation --config-settings editable_mode=compat" "$LOG"

first_count=$(wc -l < "$LOG")
BIOSTAT_BOOTSTRAP_LOG="$LOG" \
BIOSTAT_BOOTSTRAP_PYTHON="$FAKE_PYTHON" \
BIOSTAT_ANALYSIS_VENV="$VENV" \
bash "$ROOT/scripts/bootstrap-analysis-venv.sh"
second_count=$(wc -l < "$LOG")
test "$first_count" = "$second_count"
