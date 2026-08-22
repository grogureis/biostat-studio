#!/usr/bin/env bash
set -euo pipefail

APP="${BIOSTAT_PACKAGED_APP:-release/mac-arm64/BioStat Studio.app}"
SIDECAR="$APP/Contents/Resources/bin/biostat-service"

test -d "$APP"
test -x "$SIDECAR"
"$SIDECAR" --self-test
