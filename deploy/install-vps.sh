#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/samannazsheyda-commits/telegram-news-agent.git}"
BRANCH="${BRANCH:-production}"
APP_DIR="/opt/bikhabar/app"
VENV_DIR="/opt/bikhabar/venv"
PYTHON_DIR="/opt/bikhabar/python"
ENV_DIR="/etc/bikhabar"
RUNTIME_ROOT="/var/lib/bikhabar/runtime"
RUNTIME_DATA="${RUNTIME_ROOT}/data"
COMMAND_DIR="${RUNTIME_ROOT}/panel_commands"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git ca-certificates curl util-linux python3 python3-pip
python3 -m pip install --upgrade uv

if ! id bikhabar >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/bikhabar --shell /usr/sbin/nologin bikhabar
fi

install -d -o bikhabar -g bikhabar -m 755 /opt/bikhabar "${PYTHON_DIR}"
install -d -o root -g root -m 700 "${ENV_DIR}"
install -d -o bikhabar -g bikhabar -m 700 "${RUNTIME_ROOT}" "${RUNTIME_DATA}" "${COMMAND_DIR}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  runuser -u bikhabar -- git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${APP_DIR}"
else
  runuser -u bikhabar -- git -C "${APP_DIR}" fetch origin "${BRANCH}"
  runuser -u bikhabar -- git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
fi

export UV_PYTHON_INSTALL_DIR="${PYTHON_DIR}"
uv python install 3.12
rm -rf "${VENV_DIR}"
uv venv --python 3.12 "${VENV_DIR}"
uv pip install --python "${VENV_DIR}/bin/python" -r "${APP_DIR}/requirements.txt"

seed_once() {
  local src="$1"
  local dst="$2"
  if [[ ! -e "${dst}" && -e "${src}" ]]; then
    install -D -o bikhabar -g bikhabar -m 600 "${src}" "${dst}"
  fi
}
seed_once "${APP_DIR}/data/custom_sources.json" "${RUNTIME_DATA}/custom_sources.json"
seed_once "${APP_DIR}/data/newsroom_settings.json" "${RUNTIME_DATA}/newsroom_settings.json"

chown -R bikhabar:bikhabar "${PYTHON_DIR}" "${VENV_DIR}" "${APP_DIR}" "${RUNTIME_ROOT}"
chmod -R a+rX "${PYTHON_DIR}" "${VENV_DIR}"
chmod 700 "${RUNTIME_ROOT}" "${RUNTIME_DATA}" "${COMMAND_DIR}"

if [[ ! -f "${ENV_DIR}/agent.env" ]]; then
  install -m 600 "${APP_DIR}/deploy/agent.env.example" "${ENV_DIR}/agent.env"
  echo "Created ${ENV_DIR}/agent.env; set TELEGRAM_BOT_TOKEN before starting production."
fi

install -m 644 "${APP_DIR}/deploy/bikhabar-agent.service" /etc/systemd/system/bikhabar-agent.service
install -m 644 "${APP_DIR}/deploy/bikhabar-panel.service" /etc/systemd/system/bikhabar-panel.service
install -m 644 "${APP_DIR}/deploy/bikhabar-deploy.service" /etc/systemd/system/bikhabar-deploy.service
install -m 644 "${APP_DIR}/deploy/bikhabar-deploy.timer" /etc/systemd/system/bikhabar-deploy.timer
install -m 644 "${APP_DIR}/deploy/bikhabar-weather.service" /etc/systemd/system/bikhabar-weather.service
install -m 644 "${APP_DIR}/deploy/bikhabar-weather.timer" /etc/systemd/system/bikhabar-weather.timer
install -m 644 "${APP_DIR}/deploy/bikhabar-air-traffic.service" /etc/systemd/system/bikhabar-air-traffic.service
install -m 644 "${APP_DIR}/deploy/bikhabar-air-traffic.timer" /etc/systemd/system/bikhabar-air-traffic.timer
systemctl daemon-reload
systemctl enable bikhabar-agent bikhabar-panel bikhabar-deploy.timer bikhabar-weather.timer bikhabar-air-traffic.timer >/dev/null
systemctl enable --now bikhabar-deploy.timer bikhabar-weather.timer bikhabar-air-traffic.timer >/dev/null

if ! grep -q '^TELEGRAM_BOT_TOKEN=replace_me$' "${ENV_DIR}/agent.env" && grep -q '^TELEGRAM_CHAT_ID=' "${ENV_DIR}/agent.env"; then
  systemctl restart bikhabar-agent
fi
systemctl restart bikhabar-panel
sleep 5
systemctl is-active --quiet bikhabar-panel
curl -fsS --max-time 10 http://127.0.0.1/login >/dev/null

if systemctl is-active --quiet bikhabar-agent; then
  echo "AGENT=active"
else
  echo "AGENT=not-started (set TELEGRAM_BOT_TOKEN in ${ENV_DIR}/agent.env)"
fi
echo "PANEL=$(systemctl is-active bikhabar-panel)"
