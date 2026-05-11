#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_SLUG="telegram-username-collector"
INSTALL_ROOT="/opt/${APP_SLUG}"
DIST_ROOT="$ROOT_DIR/dist/linux-deb"
BUILD_ROOT="$DIST_ROOT/build"
ARCH="${DEB_ARCH:-$(dpkg --print-architecture)}"
VERSION="$(
  python3 - <<'PY'
import tomllib
from pathlib import Path

payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(payload["project"]["version"])
PY
)"
PACKAGE_NAME="${APP_SLUG}_${VERSION}_${ARCH}"
PACKAGE_ROOT="$BUILD_ROOT/$PACKAGE_NAME"
APP_ROOT="$PACKAGE_ROOT$INSTALL_ROOT/app"
VENV_ROOT="$PACKAGE_ROOT$INSTALL_ROOT/venv"
DEBIAN_DIR="$PACKAGE_ROOT/DEBIAN"
RESOURCES_DIR="$APP_ROOT/resources"
EXTENSION_ZIP_SOURCE="$ROOT_DIR/dist/site-control-bridge-extension.zip"
OUTPUT_DEB="$DIST_ROOT/${PACKAGE_NAME}.deb"
CONTROL_FILE="$DEBIAN_DIR/control"
ICON_SVG="$ROOT_DIR/resources/icons/telegram-username-collector.svg"

usage() {
  cat <<'EOF'
Usage: scripts/build_linux_deb.sh [--clean]

Builds an Ubuntu .deb package for Telegram Username Collector.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$DIST_ROOT"
  echo "Cleaned $DIST_ROOT"
  exit 0
fi

if [[ $# -gt 0 ]]; then
  echo "Unknown argument: $1" >&2
  usage >&2
  exit 1
fi

for required in rsync zip convert dpkg-deb python3; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "ERROR: required tool is missing: $required" >&2
    exit 1
  fi
done

if [[ ! -f "$ICON_SVG" ]]; then
  echo "ERROR: icon source is missing: $ICON_SVG" >&2
  exit 1
fi

mkdir -p "$DIST_ROOT" "$BUILD_ROOT"
rm -rf "$PACKAGE_ROOT"
mkdir -p "$DEBIAN_DIR" "$APP_ROOT" "$RESOURCES_DIR"

"$ROOT_DIR/scripts/package_extension.sh"

rsync -a \
  --exclude '.git' \
  --exclude '.github' \
  --exclude '.venv' \
  --exclude '.site-control-kit' \
  --exclude '.codex' \
  --exclude '.pytest_cache' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'AGENT_START_HERE.md' \
  --exclude 'CODEX_STATE.md' \
  --exclude 'AUTOPILOT.yaml' \
  --exclude 'dist' \
  --exclude 'var' \
  --exclude 'TG_CONTACT' \
  --exclude 'artifacts' \
  --exclude 'docs/agent_handoff_ru' \
  --exclude 'packaging' \
  --exclude 'tests' \
  "$ROOT_DIR/" "$APP_ROOT/"

install -Dm644 "$EXTENSION_ZIP_SOURCE" "$RESOURCES_DIR/site-control-bridge-extension.zip"

python3 -m venv --system-site-packages "$VENV_ROOT"
"$VENV_ROOT/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_ROOT/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt"

find "$VENV_ROOT/lib" -type d \( -name 'tests' -o -name 'test' \) -prune -exec rm -rf {} +
find "$VENV_ROOT" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$VENV_ROOT" -type f -name '*.pyc' -delete

install -Dm755 "$ROOT_DIR/packaging/linux/telegram-username-collector.wrapper.sh" \
  "$PACKAGE_ROOT/usr/bin/telegram-username-collector"
install -Dm755 "$ROOT_DIR/packaging/linux/sitectl.wrapper.sh" \
  "$PACKAGE_ROOT/usr/bin/sitectl"
install -Dm644 "$ROOT_DIR/packaging/linux/telegram-username-collector.desktop" \
  "$PACKAGE_ROOT/usr/share/applications/telegram-username-collector.desktop"
install -Dm644 "$ICON_SVG" \
  "$PACKAGE_ROOT/usr/share/icons/hicolor/scalable/apps/telegram-username-collector.svg"

for size in 64 128 256; do
  target="$PACKAGE_ROOT/usr/share/icons/hicolor/${size}x${size}/apps/telegram-username-collector.png"
  mkdir -p "$(dirname "$target")"
  convert -background none "$ICON_SVG" -resize "${size}x${size}" "$target"
done

cat >"$CONTROL_FILE" <<EOF
Package: $APP_SLUG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3, python3-gi, gir1.2-gtk-4.0, libgtk-4-1, xdg-utils, zip
Maintainer: Site Control Kit Contributors
Description: Telegram Username Collector desktop product for Ubuntu 24.04
 Linux-first desktop product for Telegram Username Collector.
 Installs the GTK application, desktop launcher, icon, browser bridge companion zip,
 and bundled Python dependencies under /opt/telegram-username-collector.
 User runtime data stays in XDG config/data/state directories.
EOF

dpkg-deb --build --root-owner-group "$PACKAGE_ROOT" "$OUTPUT_DEB"
echo "Built package: $OUTPUT_DEB"
