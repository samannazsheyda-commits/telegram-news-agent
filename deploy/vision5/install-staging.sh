#!/usr/bin/env bash
set -euo pipefail

source_dir="${1:-$(pwd)}"
app_root="/opt/bikhabar-vision5"
current_root="${app_root}/current"
env_root="/etc/bikhabar"
data_root="/var/lib/bikhabar/vision5"
log_root="/var/log/bikhabar/vision5"

if [[ ! -f "${source_dir}/requirements.txt" || ! -d "${source_dir}/bikhabar_v5" ]]; then
  echo "Vision 5 source tree not found: ${source_dir}" >&2
  exit 2
fi

if ! id -u bikhabar-v5 >/dev/null 2>&1; then
  useradd --system --home-dir "${app_root}" --shell /usr/sbin/nologin bikhabar-v5
fi

install -d -m 0755 -o root -g root "${app_root}" "${current_root}" "${env_root}"
install -d -m 0750 -o bikhabar-v5 -g bikhabar-v5 "${data_root}" "${data_root}/backups" "${log_root}"
rsync -a --exclude '.git' --exclude '__pycache__' "${source_dir}/" "${current_root}/"
python3 -m venv "${app_root}/venv"
"${app_root}/venv/bin/pip" install --requirement "${current_root}/requirements.txt"
chown -R root:root "${current_root}" "${app_root}/venv"

if [[ ! -f "${env_root}/v5.env" ]]; then
  install -m 0600 -o root -g root "${current_root}/deploy/vision5/v5.env.example" "${env_root}/v5.env"
  echo "Edit ${env_root}/v5.env before starting Vision 5." >&2
  exit 3
fi

install -m 0644 "${current_root}"/deploy/vision5/*.service /etc/systemd/system/
install -m 0644 "${current_root}"/deploy/vision5/*.timer /etc/systemd/system/
systemctl daemon-reload
"${app_root}/venv/bin/python" -m bikhabar_v5.preflight
"${app_root}/venv/bin/python" -m bikhabar_v5.runtime init-db
systemctl enable --now bikhabar-v5-panel.service bikhabar-v5-translation.service bikhabar-v5-publisher.service
systemctl enable --now bikhabar-v5-collector.timer bikhabar-v5-monitor.timer bikhabar-v5-backup.timer bikhabar-v5-observation.timer

echo "Vision 5 staging is listening on 127.0.0.1:8505. Legacy services were not changed."
