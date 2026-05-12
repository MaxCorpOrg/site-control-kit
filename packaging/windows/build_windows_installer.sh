#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:-$(python3 - <<'PY'
from pathlib import Path
for line in Path("pyproject.toml").read_text(encoding="utf-8").splitlines():
    if line.startswith("version = "):
        print(line.split("=", 1)[1].strip().strip('"'))
        break
PY
)}"
BUILD_DIR="${ROOT_DIR}/packaging/build/windows"
DIST_DIR="${ROOT_DIR}/packaging/dist/windows"
ICON_PATH="${BUILD_DIR}/telegram-control-center.ico"

mkdir -p "${BUILD_DIR}" "${DIST_DIR}"
python3 "${ROOT_DIR}/packaging/windows/make_icon.py" "${ICON_PATH}" >/dev/null

if [[ "${2:-}" == "--check-tools" ]]; then
  missing=0
  for tool in wine winepath; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "missing: $tool" >&2
      missing=1
    fi
  done
  if [[ "$missing" -ne 0 ]]; then
    exit 12
  fi
  echo "wine toolchain is available"
  exit 0
fi

if ! command -v wine >/dev/null 2>&1; then
  echo "ERROR: wine is required for Windows packaging on Linux." >&2
  exit 12
fi

if ! wine python -m pip --version >/dev/null 2>&1; then
  echo "ERROR: Wine Python with pip is required. Install Windows Python in this Wine prefix first." >&2
  exit 13
fi

wine python -m pip install --upgrade pyinstaller
SITE_CONTROL_KIT_RELEASE_VERSION="${VERSION}" \
  wine python -m PyInstaller --clean --noconfirm "${ROOT_DIR}/packaging/windows/TelegramControlCenter.spec" \
  --distpath "${BUILD_DIR}/dist" \
  --workpath "${BUILD_DIR}/work"

if command -v iscc >/dev/null 2>&1; then
  SITE_CONTROL_KIT_RELEASE_VERSION="${VERSION}" iscc "${ROOT_DIR}/packaging/windows/TelegramControlCenter.iss"
elif wine cmd /c iscc /? >/dev/null 2>&1; then
  SITE_CONTROL_KIT_RELEASE_VERSION="${VERSION}" wine cmd /c iscc "$(winepath -w "${ROOT_DIR}/packaging/windows/TelegramControlCenter.iss")"
else
  echo "ERROR: Inno Setup compiler (iscc) is required." >&2
  exit 14
fi

echo "${DIST_DIR}/TelegramControlCenterSetup-${VERSION}.exe"
