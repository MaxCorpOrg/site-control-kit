#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${HOME}/.cache/site-control-kit/novnc"
X11VNC_PID_FILE="${STATE_DIR}/x11vnc.pid"
WEBSOCKIFY_PID_FILE="${STATE_DIR}/websockify.pid"

stop_pid_file() {
  local pid_file="$1"
  if [[ ! -f "${pid_file}" ]]; then
    return
  fi
  local pid
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  if [[ -n "${pid}" ]]; then
    kill "${pid}" >/dev/null 2>&1 || true
    sleep 0.3
    kill -9 "${pid}" >/dev/null 2>&1 || true
  fi
  rm -f "${pid_file}"
}

stop_pid_file "${WEBSOCKIFY_PID_FILE}"
stop_pid_file "${X11VNC_PID_FILE}"

echo "INFO: noVNC bridge stopped."
