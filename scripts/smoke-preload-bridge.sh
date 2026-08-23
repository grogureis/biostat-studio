#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRELOAD="${BIOSTAT_PRELOAD:-$ROOT/apps/desktop/electron-dist/preload.cjs}"
ELECTRON="${BIOSTAT_ELECTRON:-$ROOT/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron}"

test -f "$PRELOAD"
test -x "$ELECTRON"

BIOSTAT_PRELOAD="$PRELOAD" "$ELECTRON" "$ROOT/scripts/tests/preload-bridge-harness.mjs" 2>&1 \
  | grep -v "NODE_OPTIONs are not supported" \
  | tee /dev/stderr \
  | grep -q "^preload_bridge_smoke_passed:"
