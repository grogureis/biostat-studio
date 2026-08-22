#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE_ROOT="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_ROOT"' EXIT

mkdir -p "$FIXTURE_ROOT/bin"
CALLS="$FIXTURE_ROOT/npm-calls.txt"
export BIOSTAT_TEST_ALL_CALLS="$CALLS"
cp "$ROOT/scripts/tests/fixtures/failing-python-npm" "$FIXTURE_ROOT/bin/npm"
chmod +x "$FIXTURE_ROOT/bin/npm"

set +e
PATH="$FIXTURE_ROOT/bin:$PATH" bash "$ROOT/scripts/test-all.sh"
status=$?
set -e

test "$status" -ne 0
test "$(sed -n '1p' "$CALLS")" = "run test:python"
test "$(sed -n '2p' "$CALLS")" = "run test:desktop"
test "$(wc -l < "$CALLS" | tr -d ' ')" = "2"
