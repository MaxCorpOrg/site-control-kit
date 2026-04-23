#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -eq 0 ]]; then
  exec "$ROOT_DIR/start-firefox.sh" --url "https://web.telegram.org/a/"
fi

case "$1" in
  -h|--help)
    exec "$ROOT_DIR/start-firefox.sh" --help
    ;;
  --url)
    exec "$ROOT_DIR/start-firefox.sh" "$@"
    ;;
  *)
    exec "$ROOT_DIR/start-firefox.sh" --url "$1" "${@:2}"
    ;;
esac
