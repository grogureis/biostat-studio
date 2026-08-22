#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d /private/tmp/biostat-bootstrap-test.XXXXXX)"
trap 'rm -rf "$TEST_ROOT"' EXIT

FAKE_PYTHON="$TEST_ROOT/python3"
VENV="$TEST_ROOT/analysis-venv"
LOG="$TEST_ROOT/bootstrap.log"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'if test "$1" = "-m" && test "$2" = "venv"; then' \
  '  printf "venv %s\\n" "$3" >> "$BIOSTAT_BOOTSTRAP_LOG"' \
  '  mkdir -p "$3/bin"' \
  '  printf "%s\\n" "#!/usr/bin/env bash" "set -euo pipefail" "printf '\''pip %s\\n'\'' \"$*\" >> \"\$BIOSTAT_BOOTSTRAP_LOG\"" > "$3/bin/python"' \
  '  chmod +x "$3/bin/python"' \
  '  exit 0' \
  'fi' \
  'printf "unexpected %s\\n" "$*" >> "$BIOSTAT_BOOTSTRAP_LOG"' \
  'exit 1' > "$FAKE_PYTHON"
chmod +x "$FAKE_PYTHON"

BIOSTAT_BOOTSTRAP_LOG="$LOG" \
BIOSTAT_BOOTSTRAP_PYTHON="$FAKE_PYTHON" \
BIOSTAT_ANALYSIS_VENV="$VENV" \
bash "$ROOT/scripts/bootstrap-analysis-venv.sh"

test -f "$VENV/.biostat-requirements.sha256"
grep -Fqx "venv $VENV" "$LOG"
grep -Fq "pip -m pip install --disable-pip-version-check --no-input --requirement $ROOT/services/analysis/requirements.lock" "$LOG"
grep -Fq "pip -m pip install --disable-pip-version-check --no-input --no-deps -e $ROOT/services/analysis" "$LOG"

first_count=$(wc -l < "$LOG")
BIOSTAT_BOOTSTRAP_LOG="$LOG" \
BIOSTAT_BOOTSTRAP_PYTHON="$FAKE_PYTHON" \
BIOSTAT_ANALYSIS_VENV="$VENV" \
bash "$ROOT/scripts/bootstrap-analysis-venv.sh"
second_count=$(wc -l < "$LOG")
test "$first_count" = "$second_count"
