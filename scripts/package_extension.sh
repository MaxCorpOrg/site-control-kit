#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/dist"
ZIP_NAME="site-control-bridge-extension.zip"

mkdir -p "$OUT_DIR"
cd "$ROOT_DIR/extension"
zip -r "$OUT_DIR/$ZIP_NAME" . -x '*.DS_Store' >/dev/null

echo "Created: $OUT_DIR/$ZIP_NAME"
