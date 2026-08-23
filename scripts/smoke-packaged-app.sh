#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${BIOSTAT_PACKAGED_APP:-release/mac-arm64/BioStat Studio.app}"
SIDECAR="$APP/Contents/Resources/bin/biostat-service"
ASAR="$APP/Contents/Resources/app.asar"
ASAR_TOOL="${BIOSTAT_ASAR_TOOL:-$ROOT/node_modules/.bin/asar}"
NODE="${BIOSTAT_NODE:-$(command -v node)}"
RENDERER_ROOT="$(mktemp -d /private/tmp/biostat-renderer-smoke.XXXXXX)"
trap 'rm -rf "$RENDERER_ROOT"' EXIT

test -d "$APP"
test -x "$SIDECAR"
test -f "$ASAR"
test -x "$ASAR_TOOL"
"$ASAR_TOOL" extract "$ASAR" "$RENDERER_ROOT"
# The sandboxed preload must ship as self-contained CommonJS; an ESM preload
# fails to load and silently strips window.biostat from the renderer.
test -f "$RENDERER_ROOT/electron-dist/preload.cjs"
test ! -e "$RENDERER_ROOT/electron-dist/preload.js"
grep -q 'preload\.cjs' "$RENDERER_ROOT/electron-dist/main.js"
! grep -qE '^\s*(import|export) ' "$RENDERER_ROOT/electron-dist/preload.cjs"
BIOSTAT_PRELOAD="$RENDERER_ROOT/electron-dist/preload.cjs" bash "$ROOT/scripts/smoke-preload-bridge.sh"
"$NODE" --input-type=module -e '
  import { existsSync, readFileSync } from "node:fs";
  import { fileURLToPath, pathToFileURL } from "node:url";

  const indexPath = process.argv[1];
  const html = readFileSync(indexPath, "utf8");
  // Only script and stylesheet references must resolve inside the package;
  // anchors, data: URIs, and external hrefs are not packaging failures.
  const references = [
    ...html.matchAll(/<script[^>]*\ssrc="([^"]+)"/g),
    ...html.matchAll(/<link[^>]*\brel="stylesheet"[^>]*\bhref="([^"]+)"/g),
  ].map((match) => match[1]);
  if (references.length === 0) {
    throw new Error("packaged_renderer_has_no_assets");
  }
  for (const reference of references) {
    const resolved = new URL(reference, pathToFileURL(indexPath));
    if (resolved.protocol !== "file:" || !existsSync(fileURLToPath(resolved))) {
      throw new Error(`packaged_renderer_asset_unresolved:${reference}:${resolved.href}`);
    }
  }
' "$RENDERER_ROOT/dist/index.html"
"$SIDECAR" --self-test
