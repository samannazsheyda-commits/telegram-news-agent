#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/bikhabar/app"
VENV_DIR="/opt/bikhabar/venv"
SNAPSHOT_DIR="/var/lib/bikhabar/runtime-snapshot"
ENV_FILE="/etc/bikhabar/agent.env"
PANEL_PASSWORD_FILE="/var/lib/bikhabar/panel_password.txt"
BRANCH="${BRANCH:-production}"

if [[ -f "${ENV_FILE}" ]]; then
  ENV_BRANCH="$(grep -m1 '^DEPLOY_BRANCH=' "${ENV_FILE}" | cut -d= -f2- || true)"
  if [[ -n "${ENV_BRANCH}" ]]; then
    BRANCH="${ENV_BRANCH}"
  fi
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

runuser -u bikhabar -- git -C "${APP_DIR}" fetch origin "${BRANCH}:refs/remotes/origin/${BRANCH}"
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
  [[ -f "${APP_DIR}/deploy/bikhabar-panel.service" ]] && install -m 644 "${APP_DIR}/deploy/bikhabar-panel.service" /etc/systemd/system/bikhabar-panel.service || true
  systemctl daemon-reload || true
  systemctl restart bikhabar-agent || true
  systemctl restart bikhabar-panel || true
}
trap rollback ERR

systemctl stop bikhabar-agent || true
systemctl stop bikhabar-panel || true
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

install -d -o bikhabar -g bikhabar -m 700 /var/lib/bikhabar
if ! grep -q '^PANEL_SECRET_KEY=' "${ENV_FILE}"; then
  PANEL_SECRET_KEY_VALUE="$(openssl rand -hex 32)"
  echo "PANEL_SECRET_KEY=${PANEL_SECRET_KEY_VALUE}" >> "${ENV_FILE}"
fi
if ! grep -q '^PANEL_PASSWORD_HASH=' "${ENV_FILE}"; then
  PANEL_PASSWORD_VALUE="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 18)"
  PANEL_PASSWORD_HASH_VALUE="$("${VENV_DIR}/bin/python" -c 'from werkzeug.security import generate_password_hash; import sys; print(generate_password_hash(sys.argv[1]))' "${PANEL_PASSWORD_VALUE}")"
  echo "PANEL_PASSWORD_HASH=${PANEL_PASSWORD_HASH_VALUE}" >> "${ENV_FILE}"
  printf '%s\n' "${PANEL_PASSWORD_VALUE}" > "${PANEL_PASSWORD_FILE}"
  chmod 600 "${PANEL_PASSWORD_FILE}"
fi
if ! grep -q '^PANEL_LOCAL_ROOT=' "${ENV_FILE}"; then
  echo "PANEL_LOCAL_ROOT=${APP_DIR}" >> "${ENV_FILE}"
fi

chown -R bikhabar:bikhabar "${APP_DIR}" "${SNAPSHOT_DIR}"
install -m 644 "${APP_DIR}/deploy/bikhabar-agent.service" /etc/systemd/system/bikhabar-agent.service
install -m 644 "${APP_DIR}/deploy/bikhabar-panel.service" /etc/systemd/system/bikhabar-panel.service
install -m 644 "${APP_DIR}/deploy/bikhabar-weather.service" /etc/systemd/system/bikhabar-weather.service
install -m 644 "${APP_DIR}/deploy/bikhabar-weather.timer" /etc/systemd/system/bikhabar-weather.timer
systemctl daemon-reload
systemctl enable bikhabar-agent bikhabar-panel bikhabar-weather.timer >/dev/null
systemctl restart bikhabar-agent
systemctl restart bikhabar-panel
systemctl enable --now bikhabar-weather.timer >/dev/null
sleep 8
systemctl is-active --quiet bikhabar-agent
systemctl is-active --quiet bikhabar-panel
curl -fsS --max-time 10 http://127.0.0.1:8080/login >/dev/null
trap - ERR

echo "Deployed ${TARGET_SHA} successfully"
echo "AGENT=$(systemctl is-active bikhabar-agent)"
echo "PANEL=$(systemctl is-active bikhabar-panel)"
echo "WEATHER_TIMER=$(systemctl is-active bikhabar-weather.timer)"
