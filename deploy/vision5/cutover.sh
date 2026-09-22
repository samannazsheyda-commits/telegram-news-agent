#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm-cutover" || "$#" -ne 5 ]]; then
  echo "usage: $0 --confirm-cutover CURRENT_NGINX_SITE V5_NGINX_SITE BACKUP_DIR LEGACY_UNIT_LIST" >&2
  exit 2
fi

current_site="$2"
v5_site="$3"
backup_dir="$4"
legacy_unit_list="$5"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="${backup_dir}/nginx-before-v5-${stamp}.conf"

curl --fail --silent --show-error http://127.0.0.1:8505/healthz >/dev/null
install -d -m 0700 "${backup_dir}"
cp --preserve=mode,ownership,timestamps "${current_site}" "${backup_file}"
install -m 0644 "${v5_site}" "${current_site}"
nginx -t
systemctl reload nginx

read -r -a legacy_units <<<"${legacy_unit_list}"
for unit in "${legacy_units[@]}"; do
  [[ -n "${unit}" ]] && systemctl stop "${unit}"
done

echo "CUTOVER_OK backup=${backup_file}"
