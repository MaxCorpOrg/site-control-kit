#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-default}"

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

cd "$ROOT_DIR"

run python3 -m unittest discover -s tests -p 'test_*.py'
run python3 -m webcontrol --help
run python3 -m webcontrol browser --help

if [[ "$MODE" == "--live-browser" ]]; then
  run python3 -m webcontrol browser status
  run python3 -m webcontrol browser tabs
  run python3 -m webcontrol browser open https://example.com
  run python3 -m webcontrol browser text h1
fi

printf '\nOK: verification finished (%s)\n' "$MODE"
