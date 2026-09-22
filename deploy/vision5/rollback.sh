#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm-rollback" || "$#" -ne 4 ]]; then
  echo "usage: $0 --confirm-rollback NGINX_BACKUP CURRENT_NGINX_SITE LEGACY_UNIT_LIST" >&2
  exit 2
fi

backup_file="$2"
current_site="$3"
legacy_unit_list="$4"

if [[ ! -f "${backup_file}" ]]; then
  echo "rollback backup not found: ${backup_file}" >&2
  exit 3
fi

systemctl stop bikhabar-v5-panel.service bikhabar-v5-translation.service bikhabar-v5-publisher.service
systemctl stop bikhabar-v5-collector.timer bikhabar-v5-monitor.timer bikhabar-v5-backup.timer
cp --preserve=mode,ownership,timestamps "${backup_file}" "${current_site}"
nginx -t
systemctl reload nginx

read -r -a legacy_units <<<"${legacy_unit_list}"
for unit in "${legacy_units[@]}"; do
  [[ -n "${unit}" ]] && systemctl start "${unit}"
done

echo "ROLLBACK_OK restored=${backup_file}"
