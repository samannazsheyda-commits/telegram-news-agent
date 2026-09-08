#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/bikhabar/app"
VENV_DIR="/opt/bikhabar/venv"
SNAPSHOT_DIR="/var/lib/bikhabar/runtime-snapshot"
ENV_FILE="/etc/bikhabar/agent.env"
BRANCH="${BRANCH:-production}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  BRANCH="${DEPLOY_BRANCH:-${BRANCH}}"
fi

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

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "Missing git checkout at ${APP_DIR}" >&2
  exit 1
fi

runuser -u bikhabar -- git -C "${APP_DIR}" fetch origin "${BRANCH}"
CURRENT_SHA="$(git -C "${APP_DIR}" rev-parse HEAD)"
TARGET_SHA="$(git -C "${APP_DIR}" rev-parse "origin/${BRANCH}")"

if [[ "${CURRENT_SHA}" == "${TARGET_SHA}" ]]; then
  echo "Already up to date at ${CURRENT_SHA}"
  exit 0
fi

mkdir -p "${SNAPSHOT_DIR}/data"
for path in "${RUNTIME_FILES[@]}"; do
  if [[ -f "${APP_DIR}/${path}" ]]; then
    mkdir -p "${SNAPSHOT_DIR}/$(dirname "${path}")"
    cp -a "${APP_DIR}/${path}" "${SNAPSHOT_DIR}/${path}"
  fi
done

rollback() {
  echo "Deploy failed; rolling back to ${CURRENT_SHA}" >&2
  runuser -u bikhabar -- git -C "${APP_DIR}" reset --hard "${CURRENT_SHA}" || true
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "${VENV_DIR}/bin/python" -r "${APP_DIR}/requirements.txt" || true
  fi
  for path in "${RUNTIME_FILES[@]}"; do
    if [[ -f "${SNAPSHOT_DIR}/${path}" ]]; then
      mkdir -p "${APP_DIR}/$(dirname "${path}")"
      cp -a "${SNAPSHOT_DIR}/${path}" "${APP_DIR}/${path}"
    fi
  done
  chown -R bikhabar:bikhabar "${APP_DIR}" "${SNAPSHOT_DIR}" || true
  install -m 644 "${APP_DIR}/deploy/bikhabar-agent.service" /etc/systemd/system/bikhabar-agent.service || true
  systemctl daemon-reload || true
  systemctl restart bikhabar-agent || true
}
trap rollback ERR

systemctl stop bikhabar-agent || true
runuser -u bikhabar -- git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"

if command -v uv >/dev/null 2>&1; then
  uv pip install --python "${VENV_DIR}/bin/python" -r "${APP_DIR}/requirements.txt"
else
  "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"
fi

for path in "${RUNTIME_FILES[@]}"; do
  if [[ -f "${SNAPSHOT_DIR}/${path}" ]]; then
    mkdir -p "${APP_DIR}/$(dirname "${path}")"
    cp -a "${SNAPSHOT_DIR}/${path}" "${APP_DIR}/${path}"
  fi
done

chown -R bikhabar:bikhabar "${APP_DIR}" "${SNAPSHOT_DIR}"
install -m 644 "${APP_DIR}/deploy/bikhabar-agent.service" /etc/systemd/system/bikhabar-agent.service
systemctl daemon-reload
systemctl restart bikhabar-agent
sleep 8
systemctl is-active --quiet bikhabar-agent
trap - ERR

echo "Deployed ${TARGET_SHA} successfully"
systemctl --no-pager --full status bikhabar-agent | head -n 20
