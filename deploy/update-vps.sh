#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/bikhabar/app"
VENV_DIR="/opt/bikhabar/venv"
RUNTIME_ROOT="/var/lib/bikhabar/runtime"
RUNTIME_DATA="${RUNTIME_ROOT}/data"
COMMAND_DIR="${RUNTIME_ROOT}/panel_commands"
ENV_FILE="/etc/bikhabar/agent.env"
PANEL_PASSWORD_FILE="/var/lib/bikhabar/panel_password.txt"
BRANCH="${BRANCH:-production}"

if [[ -f "${ENV_FILE}" ]]; then
  ENV_BRANCH="$(grep -m1 '^DEPLOY_BRANCH=' "${ENV_FILE}" | cut -d= -f2- || true)"
  [[ -n "${ENV_BRANCH}" ]] && BRANCH="${ENV_BRANCH}"
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this updater as root." >&2
  exit 1
fi
if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "Missing git checkout at ${APP_DIR}" >&2
  exit 1
fi

# The air-traffic image embeds Persian text. Existing VPS installs may predate
# this renderer, so repair the font dependency once if it is missing.
if [[ ! -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ]]; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y fonts-dejavu-core
fi

install -d -o bikhabar -g bikhabar -m 700 "${RUNTIME_ROOT}" "${RUNTIME_DATA}" "${COMMAND_DIR}"

chown -R bikhabar:bikhabar "${APP_DIR}"

migrate_once() {
  local src="$1"
  local dst="$2"
  if [[ ! -e "${dst}" && -e "${src}" ]]; then
    install -D -o bikhabar -g bikhabar -m 600 "${src}" "${dst}"
  fi
}

migrate_once "${APP_DIR}/state.json" "${RUNTIME_ROOT}/state.json"
migrate_once "${APP_DIR}/data/newsroom_settings.json" "${RUNTIME_DATA}/newsroom_settings.json"
migrate_once "${APP_DIR}/data/custom_sources.json" "${RUNTIME_DATA}/custom_sources.json"
migrate_once "${APP_DIR}/data/editorial_queue.json" "${RUNTIME_DATA}/editorial_queue.json"
migrate_once "${APP_DIR}/data/editorial_history.json" "${RUNTIME_DATA}/editorial_history.json"
migrate_once "${APP_DIR}/data/event_ledger.json" "${RUNTIME_DATA}/event_ledger.json"
migrate_once "${APP_DIR}/data/panel_live_feed.json" "${RUNTIME_DATA}/panel_live_feed.json"
if [[ -d "${APP_DIR}/panel_commands" ]]; then
  find "${APP_DIR}/panel_commands" -maxdepth 1 -type f -name '*.json' -exec cp -n {} "${COMMAND_DIR}/" \; || true
fi

runuser -u bikhabar -- git -C "${APP_DIR}" fetch origin "${BRANCH}:refs/remotes/origin/${BRANCH}"
CURRENT_SHA="$(runuser -u bikhabar -- git -C "${APP_DIR}" rev-parse HEAD)"
TARGET_SHA="$(runuser -u bikhabar -- git -C "${APP_DIR}" rev-parse "origin/${BRANCH}")"

if [[ "${CURRENT_SHA}" == "${TARGET_SHA}" ]]; then
  echo "Already up to date at ${CURRENT_SHA}"
else
  rollback() {
    echo "Deploy failed; rolling code back to ${CURRENT_SHA}" >&2
    runuser -u bikhabar -- git -C "${APP_DIR}" reset --hard "${CURRENT_SHA}" || true
    if command -v uv >/dev/null 2>&1; then
      uv pip install --python "${VENV_DIR}/bin/python" -r "${APP_DIR}/requirements.txt" || true
    else
      "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt" || true
    fi
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
fi

seed_once() {
  local src="$1"
  local dst="$2"
  if [[ ! -e "${dst}" && -e "${src}" ]]; then
    install -D -o bikhabar -g bikhabar -m 600 "${src}" "${dst}"
  fi
}
seed_once "${APP_DIR}/data/custom_sources.json" "${RUNTIME_DATA}/custom_sources.json"
seed_once "${APP_DIR}/data/newsroom_settings.json" "${RUNTIME_DATA}/newsroom_settings.json"

install -d -o bikhabar -g bikhabar -m 700 /var/lib/bikhabar
if ! grep -q '^PANEL_SECRET_KEY=' "${ENV_FILE}"; then
  echo "PANEL_SECRET_KEY=$(openssl rand -hex 32)" >> "${ENV_FILE}"
fi
if ! grep -q '^PANEL_PASSWORD_HASH=' "${ENV_FILE}"; then
  PANEL_PASSWORD_VALUE="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 18)"
  PANEL_PASSWORD_HASH_VALUE="$("${VENV_DIR}/bin/python" -c 'from werkzeug.security import generate_password_hash; import sys; print(generate_password_hash(sys.argv[1]))' "${PANEL_PASSWORD_VALUE}")"
  echo "PANEL_PASSWORD_HASH=${PANEL_PASSWORD_HASH_VALUE}" >> "${ENV_FILE}"
  printf '%s\n' "${PANEL_PASSWORD_VALUE}" > "${PANEL_PASSWORD_FILE}"
  chmod 600 "${PANEL_PASSWORD_FILE}"
fi

for pair in \
  "BIKHABAR_RUNTIME_ROOT=${RUNTIME_ROOT}" \
  "STATE_PATH=${RUNTIME_ROOT}/state.json" \
  "DATA_DIR=${RUNTIME_DATA}" \
  "CUSTOM_SOURCES_PATH=${RUNTIME_DATA}/custom_sources.json" \
  "NEWSROOM_SETTINGS_PATH=${RUNTIME_DATA}/newsroom_settings.json" \
  "PANEL_LOCAL_ROOT=${RUNTIME_ROOT}" \
  "PANEL_COMMAND_DIR=${COMMAND_DIR}" \
  "PANEL_COOKIE_SECURE=0" \
  "POLL_SECONDS=2" \
  "SESSION_SECONDS=0"; do
  key="${pair%%=*}"
  value="${pair#*=}"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s#^${key}=.*#${key}=${value}#" "${ENV_FILE}"
  else
    echo "${key}=${value}" >> "${ENV_FILE}"
  fi
done

chown -R bikhabar:bikhabar "${RUNTIME_ROOT}" "${APP_DIR}"
chmod 700 "${RUNTIME_ROOT}" "${RUNTIME_DATA}" "${COMMAND_DIR}"

install -m 644 "${APP_DIR}/deploy/bikhabar-agent.service" /etc/systemd/system/bikhabar-agent.service
install -m 644 "${APP_DIR}/deploy/bikhabar-panel.service" /etc/systemd/system/bikhabar-panel.service
install -m 644 "${APP_DIR}/deploy/bikhabar-weather.service" /etc/systemd/system/bikhabar-weather.service
install -m 644 "${APP_DIR}/deploy/bikhabar-weather.timer" /etc/systemd/system/bikhabar-weather.timer
install -m 644 "${APP_DIR}/deploy/bikhabar-air-traffic.service" /etc/systemd/system/bikhabar-air-traffic.service
install -m 644 "${APP_DIR}/deploy/bikhabar-air-traffic.timer" /etc/systemd/system/bikhabar-air-traffic.timer
systemctl daemon-reload
systemctl enable bikhabar-agent bikhabar-panel bikhabar-weather.timer bikhabar-air-traffic.timer >/dev/null
systemctl restart bikhabar-agent
systemctl restart bikhabar-panel
systemctl enable --now bikhabar-weather.timer bikhabar-air-traffic.timer >/dev/null
# The timer unit may already be active; restart it so changed OnCalendar lines take effect immediately.
systemctl restart bikhabar-air-traffic.timer
sleep 6
systemctl is-active --quiet bikhabar-agent
systemctl is-active --quiet bikhabar-panel
systemctl is-active --quiet bikhabar-weather.timer
systemctl is-active --quiet bikhabar-air-traffic.timer
curl -fsS --max-time 10 http://127.0.0.1/login >/dev/null
trap - ERR

echo "Deployed ${TARGET_SHA} successfully"
echo "AGENT=$(systemctl is-active bikhabar-agent)"
echo "PANEL=$(systemctl is-active bikhabar-panel)"
echo "WEATHER_TIMER=$(systemctl is-active bikhabar-weather.timer)"
echo "AIR_TRAFFIC_TIMER=$(systemctl is-active bikhabar-air-traffic.timer)"
