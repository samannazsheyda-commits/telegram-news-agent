#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/samannazsheyda-commits/telegram-news-agent.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="/opt/bikhabar/app"
VENV_DIR="/opt/bikhabar/venv"
ENV_DIR="/etc/bikhabar"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip ca-certificates

if ! id bikhabar >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/bikhabar --shell /usr/sbin/nologin bikhabar
fi

mkdir -p /opt/bikhabar "${ENV_DIR}" /var/lib/bikhabar/runtime-snapshot
chown -R bikhabar:bikhabar /opt/bikhabar /var/lib/bikhabar

if [[ ! -d "${APP_DIR}/.git" ]]; then
  sudo -u bikhabar git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${APP_DIR}"
else
  sudo -u bikhabar git -C "${APP_DIR}" fetch origin "${BRANCH}"
  sudo -u bikhabar git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
fi

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"
chown -R bikhabar:bikhabar "${VENV_DIR}" "${APP_DIR}"

if [[ ! -f "${ENV_DIR}/agent.env" ]]; then
  install -m 600 "${APP_DIR}/deploy/agent.env.example" "${ENV_DIR}/agent.env"
  echo
  echo "Created ${ENV_DIR}/agent.env. Put TELEGRAM_BOT_TOKEN in that file, then run:"
  echo "  systemctl enable --now bikhabar-agent"
fi

install -m 644 "${APP_DIR}/deploy/bikhabar-agent.service" /etc/systemd/system/bikhabar-agent.service
systemctl daemon-reload

if ! grep -q '^TELEGRAM_BOT_TOKEN=replace_me$' "${ENV_DIR}/agent.env"; then
  systemctl enable --now bikhabar-agent
  systemctl --no-pager --full status bikhabar-agent || true
fi
