#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

if [[ $# -eq 0 ]]; then
  exec ./start-browser.sh --url "https://web.telegram.org/a/"
fi

case "$1" in
  -h|--help)
    exec ./start-browser.sh --help
    ;;
  --url)
    exec ./start-browser.sh "$@"
    ;;
  *)
    exec ./start-browser.sh --url "$1" "${@:2}"
    ;;
esac
