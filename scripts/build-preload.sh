#!/usr/bin/env bash
set -euo pipefail

# Electron loads a sandboxed preload as CommonJS and gives it no relative
# module resolution, so preload.ts and everything it imports must ship as one
# self-contained CJS file. tsc cannot produce that here; esbuild bundles it.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ESBUILD="${BIOSTAT_ESBUILD:-$ROOT/node_modules/.bin/esbuild}"
OUT="$ROOT/apps/desktop/electron-dist/preload.cjs"

test -x "$ESBUILD"
mkdir -p "$(dirname "$OUT")"
# A stale ESM preload.js from an earlier build must never be packaged.
rm -f "$ROOT/apps/desktop/electron-dist/preload.js"
"$ESBUILD" "$ROOT/apps/desktop/electron/preload.ts" \
  --bundle \
  --platform=node \
  --format=cjs \
  --target=node20 \
  --external:electron \
  --outfile="$OUT" \
  --log-level=warning
