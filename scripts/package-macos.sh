#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYSIS_VENV="${BIOSTAT_ANALYSIS_VENV:-$ROOT/services/analysis/.venv-py312}"
PYTHON="$ANALYSIS_VENV/bin/python"
PACKAGE_OUTPUT="$(mktemp -d /private/tmp/biostat-studio-release.XXXXXX)"
trap 'rm -rf "$PACKAGE_OUTPUT"' EXIT

test "$(uname -m)" = "arm64"

cd "$ROOT"
bash scripts/bootstrap-analysis-venv.sh
if ! test -x node_modules/.bin/electron-builder; then
  npm ci --no-audit --no-fund --fetch-timeout=30000 --fetch-retries=1
fi
PYINSTALLER_CONFIG_DIR=/private/tmp/biostat-task12-pyinstaller MPLCONFIGDIR=/private/tmp/biostat-task12-mpl "$PYTHON" -m PyInstaller services/analysis/biostat-service.spec --noconfirm --clean --distpath services/analysis/dist --workpath services/analysis/build
npm run build --workspace apps/desktop
npx tsc --project apps/desktop/tsconfig.electron.json
bash scripts/build-preload.sh
printf '{"type":"module"}\n' > apps/desktop/electron-dist/package.json
bash scripts/smoke-preload-bridge.sh
npx electron-builder --config electron-builder.yml --mac dmg dir --arm64 --config.directories.output="$PACKAGE_OUTPUT"
BIOSTAT_PACKAGED_APP="$PACKAGE_OUTPUT/mac-arm64/BioStat Studio.app" bash scripts/smoke-packaged-app.sh
codesign --verify --deep --strict --verbose=2 "$PACKAGE_OUTPUT/mac-arm64/BioStat Studio.app"
hdiutil verify "$PACKAGE_OUTPUT/BioStat Studio-0.1.0-arm64.dmg"
mkdir -p release
cp -f "$PACKAGE_OUTPUT/BioStat Studio-0.1.0-arm64.dmg" "release/BioStat Studio-0.1.0-arm64.dmg"
cp -f "$PACKAGE_OUTPUT/BioStat Studio-0.1.0-arm64.dmg.blockmap" "release/BioStat Studio-0.1.0-arm64.dmg.blockmap"
bash scripts/verify-package-cleanliness.sh
