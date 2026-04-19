#!/usr/bin/env bash
set -euo pipefail

DISPLAY_VALUE="${DISPLAY:-:0}"
STATE_DIR="${HOME}/.cache/site-control-kit/novnc"
VNC_PORT="${NOVNC_VNC_PORT:-5901}"
WEB_PORT="${NOVNC_WEB_PORT:-6080}"
LISTEN_HOST="${NOVNC_LISTEN_HOST:-127.0.0.1}"
VIEW_ONLY="${NOVNC_VIEW_ONLY:-0}"
X11VNC_BIN="${X11VNC_BIN:-x11vnc}"
WEBSOCKIFY_BIN="${WEBSOCKIFY_BIN:-websockify}"
NOVNC_WEB_DIR="${NOVNC_WEB_DIR:-/usr/share/novnc}"
X11VNC_PID_FILE="${STATE_DIR}/x11vnc.pid"
WEBSOCKIFY_PID_FILE="${STATE_DIR}/websockify.pid"
X11VNC_LOG="${STATE_DIR}/x11vnc.log"
WEBSOCKIFY_LOG="${STATE_DIR}/websockify.log"

mkdir -p "${STATE_DIR}"

require_bin() {
  local bin_name="$1"
  if ! command -v "${bin_name}" >/dev/null 2>&1; then
    echo "ERROR: '${bin_name}' is not installed." >&2
    exit 1
  fi
}

is_running() {
  local pid_file="$1"
  if [[ ! -f "${pid_file}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

require_bin "${X11VNC_BIN}"
require_bin "${WEBSOCKIFY_BIN}"

if [[ ! -d "${NOVNC_WEB_DIR}" ]]; then
  echo "ERROR: noVNC web dir not found: ${NOVNC_WEB_DIR}" >&2
  echo "Set NOVNC_WEB_DIR or install the noVNC package." >&2
  exit 1
fi

if is_running "${X11VNC_PID_FILE}" && is_running "${WEBSOCKIFY_PID_FILE}"; then
  echo "INFO: noVNC bridge is already running."
else
  if ! is_running "${X11VNC_PID_FILE}"; then
    x11vnc_args=(
      -display "${DISPLAY_VALUE}"
      -rfbport "${VNC_PORT}"
      -localhost
      -shared
      -forever
      -noxdamage
      -quiet
      -o "${X11VNC_LOG}"
    )
    if [[ "${VIEW_ONLY}" == "1" ]]; then
      x11vnc_args+=(-viewonly)
    fi
    nohup "${X11VNC_BIN}" "${x11vnc_args[@]}" >/dev/null 2>&1 &
    echo "$!" >"${X11VNC_PID_FILE}"
    sleep 0.8
  fi

  if ! is_running "${WEBSOCKIFY_PID_FILE}"; then
    nohup "${WEBSOCKIFY_BIN}" --web "${NOVNC_WEB_DIR}" "${LISTEN_HOST}:${WEB_PORT}" "127.0.0.1:${VNC_PORT}" \
      >"${WEBSOCKIFY_LOG}" 2>&1 &
    echo "$!" >"${WEBSOCKIFY_PID_FILE}"
    sleep 0.8
  fi
fi

query="autoconnect=1&resize=scale"
if [[ "${VIEW_ONLY}" == "1" ]]; then
  query="${query}&view_only=1"
fi

echo "URL=http://${LISTEN_HOST}:${WEB_PORT}/vnc.html?${query}"
echo "DISPLAY=${DISPLAY_VALUE}"
echo "STATE_DIR=${STATE_DIR}"
echo "X11VNC_LOG=${X11VNC_LOG}"
echo "WEBSOCKIFY_LOG=${WEBSOCKIFY_LOG}"
