#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/samannazsheyda-commits/telegram-news-agent.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="/opt/bikhabar/app"
VENV_DIR="/opt/bikhabar/venv"
PYTHON_DIR="/opt/bikhabar/python"
ENV_DIR="/etc/bikhabar"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

. /etc/os-release
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git ca-certificates curl util-linux python3 python3-pip

if ! id bikhabar >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/bikhabar --shell /usr/sbin/nologin bikhabar
fi

mkdir -p /opt/bikhabar "${PYTHON_DIR}" "${ENV_DIR}" /var/lib/bikhabar/runtime-snapshot
chown -R bikhabar:bikhabar /opt/bikhabar /var/lib/bikhabar

if [[ ! -d "${APP_DIR}/.git" ]]; then
  runuser -u bikhabar -- git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${APP_DIR}"
else
  runuser -u bikhabar -- git -C "${APP_DIR}" fetch origin "${BRANCH}"
  runuser -u bikhabar -- git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
fi

if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "20.04" ]]; then
  python3 -m pip install --upgrade uv
  export UV_PYTHON_INSTALL_DIR="${PYTHON_DIR}"
  uv python install 3.12
  rm -rf "${VENV_DIR}"
  uv venv --python 3.12 "${VENV_DIR}"
  uv pip install --python "${VENV_DIR}/bin/python" -r "${APP_DIR}/requirements.txt"
else
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv
  rm -rf "${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"
fi

chown -R bikhabar:bikhabar "${PYTHON_DIR}" "${VENV_DIR}" "${APP_DIR}"
chmod -R a+rX "${PYTHON_DIR}" "${VENV_DIR}"

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
