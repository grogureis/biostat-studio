#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

untracked=$(git status --porcelain --untracked-files=all -- \
  apps/desktop/electron-dist \
  apps/desktop/build/icon.iconset \
  apps/desktop/test-results \
  build \
  services/analysis/build)

if test -n "$untracked"; then
  printf 'Generated packaging outputs are untracked:\n%s\n' "$untracked" >&2
  exit 1
fi
