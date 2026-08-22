#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/services/analysis/.venv/bin/python"

test "$(uname -m)" = "arm64"
test -x "$PYTHON"

cd "$ROOT"
PYINSTALLER_CONFIG_DIR=/private/tmp/biostat-task12-pyinstaller MPLCONFIGDIR=/private/tmp/biostat-task12-mpl "$PYTHON" -m PyInstaller services/analysis/biostat-service.spec --noconfirm --clean --distpath services/analysis/dist --workpath services/analysis/build
npm run build --workspace apps/desktop
npx tsc --project apps/desktop/tsconfig.electron.json
printf '{"type":"module"}\n' > apps/desktop/electron-dist/package.json
npx electron-builder --config electron-builder.yml --mac dmg dir --arm64
bash scripts/smoke-packaged-app.sh
