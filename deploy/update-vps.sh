#!/usr/bin/env bash
set -euo pipefail

BRANCH="${BRANCH:-main}"
APP_DIR="/opt/bikhabar/app"
VENV_DIR="/opt/bikhabar/venv"
SNAPSHOT_DIR="/var/lib/bikhabar/runtime-snapshot"
RUNTIME_FILES=(
  "state.json"
  "data/editorial_queue.json"
  "data/editorial_history.json"
  "data/event_ledger.json"
  "data/panel_live_feed.json"
)

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this updater as root." >&2
  exit 1
fi

mkdir -p "${SNAPSHOT_DIR}/data"
systemctl stop bikhabar-agent || true

for path in "${RUNTIME_FILES[@]}"; do
  if [[ -f "${APP_DIR}/${path}" ]]; then
    mkdir -p "${SNAPSHOT_DIR}/$(dirname "${path}")"
    cp -a "${APP_DIR}/${path}" "${SNAPSHOT_DIR}/${path}"
  fi
done

sudo -u bikhabar git -C "${APP_DIR}" fetch origin "${BRANCH}"
sudo -u bikhabar git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

for path in "${RUNTIME_FILES[@]}"; do
  if [[ -f "${SNAPSHOT_DIR}/${path}" ]]; then
    mkdir -p "${APP_DIR}/$(dirname "${path}")"
    cp -a "${SNAPSHOT_DIR}/${path}" "${APP_DIR}/${path}"
  fi
done

chown -R bikhabar:bikhabar "${APP_DIR}" "${SNAPSHOT_DIR}"
install -m 644 "${APP_DIR}/deploy/bikhabar-agent.service" /etc/systemd/system/bikhabar-agent.service
systemctl daemon-reload
systemctl start bikhabar-agent
systemctl --no-pager --full status bikhabar-agent || true
