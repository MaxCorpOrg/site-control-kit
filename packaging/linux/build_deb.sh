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
BUILD_DIR="${ROOT_DIR}/packaging/build/linux-deb"
DEB_ROOT="${BUILD_DIR}/root"
APP_DIR="${DEB_ROOT}/opt/site-control-kit/app"
OUT_DIR="${ROOT_DIR}/packaging/dist/linux"
PACKAGE_NAME="telegram-control-center"
ARCH="all"

rm -rf "${BUILD_DIR}"
mkdir -p "${APP_DIR}" "${OUT_DIR}" \
  "${DEB_ROOT}/usr/bin" \
  "${DEB_ROOT}/usr/share/applications" \
  "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps" \
  "${DEB_ROOT}/DEBIAN"

cd "${ROOT_DIR}"
tar \
  --exclude='.git' \
  --exclude='.codex' \
  --exclude='TG_APP' \
  --exclude='telegram_ak' \
  --exclude='runtime' \
  --exclude='dist' \
  --exclude='build' \
  --exclude='packaging/build' \
  --exclude='packaging/dist' \
  --exclude='**/__pycache__' \
  --exclude='*.pyc' \
  -cf - \
  pyproject.toml README.md BROWSER_QUICKSTART.md \
  webcontrol tool_platform telegram_portable_session_tool tools docs packaging/assets \
  scripts/telegram_portable.py \
  scripts/telegram_invite_manager.py \
  scripts/telegram_invite_executor.py \
  scripts/export_telegram_members_non_pii.py \
  scripts/telegram_contact_chain.py \
  scripts/telegram_contact_batches.py \
  scripts/telegram_profiles.py \
  scripts/write_telegram_safe_snapshot.py \
  scripts/auto_collect_usernames.sh \
  scripts/collect_new_telegram_contacts.sh \
  scripts/collect_new_telegram_contacts_chain.sh \
  | tar -xf - -C "${APP_DIR}"

install -m 0755 packaging/linux/telegram-control-center "${DEB_ROOT}/usr/bin/telegram-control-center"
install -m 0755 packaging/linux/telegram-control-center-install-desktop-shortcut \
  "${DEB_ROOT}/usr/bin/telegram-control-center-install-desktop-shortcut"
install -m 0644 packaging/linux/telegram-control-center.desktop \
  "${DEB_ROOT}/usr/share/applications/telegram-control-center.desktop"
install -m 0644 packaging/assets/telegram-control-center.svg \
  "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps/telegram-control-center.svg"
install -m 0755 packaging/linux/postinst "${DEB_ROOT}/DEBIAN/postinst"
install -m 0755 packaging/linux/postrm "${DEB_ROOT}/DEBIAN/postrm"

cat > "${DEB_ROOT}/DEBIAN/control" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: Site Control Kit Contributors
Depends: python3 (>= 3.10), python3-tk, python3-gi, python3-xlib, python3-pil, wmctrl, xdg-utils
Description: Telegram Control Center
 Local Telegram operator control center packaged from site-control-kit.
EOF

dpkg-deb --root-owner-group --build "${DEB_ROOT}" "${OUT_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo "${OUT_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
