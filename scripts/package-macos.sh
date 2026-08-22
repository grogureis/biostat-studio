#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYSIS_VENV="${BIOSTAT_ANALYSIS_VENV:-$ROOT/services/analysis/.venv-py312}"
PYTHON="$ANALYSIS_VENV/bin/python"

test "$(uname -m)" = "arm64"

cd "$ROOT"
bash scripts/bootstrap-analysis-venv.sh
if ! test -x node_modules/.bin/electron-builder; then
  npm ci --no-audit --no-fund --fetch-timeout=30000 --fetch-retries=1
fi
PYINSTALLER_CONFIG_DIR=/private/tmp/biostat-task12-pyinstaller MPLCONFIGDIR=/private/tmp/biostat-task12-mpl "$PYTHON" -m PyInstaller services/analysis/biostat-service.spec --noconfirm --clean --distpath services/analysis/dist --workpath services/analysis/build
npm run build --workspace apps/desktop
npx tsc --project apps/desktop/tsconfig.electron.json
printf '{"type":"module"}\n' > apps/desktop/electron-dist/package.json
npx electron-builder --config electron-builder.yml --mac dmg dir --arm64
bash scripts/smoke-packaged-app.sh
bash scripts/verify-package-cleanliness.sh
