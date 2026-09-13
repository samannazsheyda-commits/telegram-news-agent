#!/usr/bin/env bash
set -euo pipefail

MODEL_ROOT="${OFFLINE_TRANSLATOR_ROOT:-/var/lib/bikhabar/models}"
MODEL_DIR="${OFFLINE_TRANSLATOR_MODEL_DIR:-${MODEL_ROOT}/argos-en-fa}"
OLD_MODEL_DIR="${MODEL_ROOT}/quickmt-en-fa"
PACKAGE_NAME="translate-en_fa-1_5.argosmodel"
URLS=(
  "https://argosopentech.nyc3.digitaloceanspaces.com/argospm/${PACKAGE_NAME}"
  "https://cdn.argosopentech.io/${PACKAGE_NAME}"
  "https://data.argosopentech.com/argospm/v1/${PACKAGE_NAME}"
)

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run offline translator installer as root." >&2
  exit 1
fi

if [[ -f "${MODEL_DIR}/model/model.bin" ]] \
  && [[ -f "${MODEL_DIR}/model/config.json" ]] \
  && [[ -f "${MODEL_DIR}/sentencepiece.model" ]]; then
  echo "OFFLINE_TRANSLATOR=ready path=${MODEL_DIR}"
  exit 0
fi

install -d -o bikhabar -g bikhabar -m 750 "${MODEL_ROOT}"
WORK_DIR="${MODEL_ROOT}/.argos-en-fa.tmp.$$"
ARCHIVE="${WORK_DIR}/${PACKAGE_NAME}"
UNPACK_DIR="${WORK_DIR}/unpacked"
INSTALL_DIR="${WORK_DIR}/install"
rm -rf "${WORK_DIR}"
mkdir -p "${UNPACK_DIR}" "${INSTALL_DIR}"
trap 'rm -rf "${WORK_DIR}"' EXIT

DOWNLOADED=0
for url in "${URLS[@]}"; do
  echo "Downloading compact offline translator: ${url}"
  if curl -fL --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 1200 \
      "${url}" -o "${ARCHIVE}"; then
    if [[ -s "${ARCHIVE}" ]] && [[ $(stat -c%s "${ARCHIVE}") -gt 50000000 ]]; then
      DOWNLOADED=1
      break
    fi
  fi
  rm -f "${ARCHIVE}"
done

if [[ "${DOWNLOADED}" -ne 1 ]]; then
  echo "Unable to download the Argos EN→FA model from all configured mirrors." >&2
  exit 1
fi

python3 - "${ARCHIVE}" "${UNPACK_DIR}" "${INSTALL_DIR}" <<'PY'
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

archive = Path(sys.argv[1])
unpack = Path(sys.argv[2])
dest = Path(sys.argv[3])

if not zipfile.is_zipfile(archive):
    raise SystemExit("Downloaded Argos package is not a valid zip archive")

with zipfile.ZipFile(archive) as zf:
    for member in zf.infolist():
        target = (unpack / member.filename).resolve()
        if unpack.resolve() not in target.parents and target != unpack.resolve():
            raise SystemExit("Unsafe path in Argos package")
    zf.extractall(unpack)

package_root = None
for model_bin in unpack.rglob("model.bin"):
    model_dir = model_bin.parent
    root = model_dir.parent
    if model_dir.name != "model":
        continue
    if not (model_dir / "config.json").is_file():
        continue
    if not (root / "sentencepiece.model").is_file():
        continue
    package_root = root
    break

if package_root is None:
    raise SystemExit("Argos package is missing model/model.bin, config.json, or sentencepiece.model")

shutil.copytree(package_root / "model", dest / "model", dirs_exist_ok=True)
shutil.copy2(package_root / "sentencepiece.model", dest / "sentencepiece.model")
metadata = package_root / "metadata.json"
if metadata.is_file():
    shutil.copy2(metadata, dest / "metadata.json")
PY

[[ -s "${INSTALL_DIR}/model/model.bin" ]]
[[ -s "${INSTALL_DIR}/model/config.json" ]]
[[ -s "${INSTALL_DIR}/sentencepiece.model" ]]

rm -rf "${MODEL_DIR}"
mv "${INSTALL_DIR}" "${MODEL_DIR}"
chown -R bikhabar:bikhabar "${MODEL_DIR}"
chmod 750 "${MODEL_DIR}"
find "${MODEL_DIR}" -type f -exec chmod 640 {} +

# Remove the old 400+ MB QuickMT package only after the compact model is safely installed.
if [[ "${OLD_MODEL_DIR}" != "${MODEL_DIR}" ]]; then
  rm -rf "${OLD_MODEL_DIR}"
fi

trap - EXIT
rm -rf "${WORK_DIR}"
echo "OFFLINE_TRANSLATOR=installed backend=argos-en-fa path=${MODEL_DIR}"
