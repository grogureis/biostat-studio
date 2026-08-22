#!/usr/bin/env bash
set -uo pipefail

python_status=0
desktop_status=0

npm run test:python || python_status=$?
npm run test:desktop || desktop_status=$?

if (( python_status != 0 || desktop_status != 0 )); then
  exit 1
fi
