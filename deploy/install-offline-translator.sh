#!/usr/bin/env bash
set -euo pipefail
MODEL_ROOT="${OFFLINE_TRANSLATOR_ROOT:-/var/lib/bikhabar/models}"
MODEL_DIR="${OFFLINE_TRANSLATOR_MODEL_DIR:-${MODEL_ROOT}/quickmt-en-fa}"
BASE_URL="https://huggingface.co/quickmt/quickmt-en-fa/resolve/main"
FILES=(config.json model.bin source_vocabulary.json target_vocabulary.json src.spm.model tgt.spm.model)

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run offline translator installer as root." >&2
  exit 1
fi

if [[ -f "${MODEL_DIR}/model.bin" ]] && [[ $(stat -c%s "${MODEL_DIR}/model.bin") -gt 300000000 ]]; then
  echo "OFFLINE_TRANSLATOR=ready path=${MODEL_DIR}"
  exit 0
fi

install -d -o bikhabar -g bikhabar -m 750 "${MODEL_ROOT}"
TMP_DIR="${MODEL_ROOT}/.quickmt-en-fa.tmp.$$"
rm -rf "${TMP_DIR}"
mkdir -p "${TMP_DIR}"
trap 'rm -rf "${TMP_DIR}"' EXIT

for file in "${FILES[@]}"; do
  echo "Downloading offline translator: ${file}"
  curl -fL --retry 4 --retry-delay 3 --connect-timeout 20 --max-time 1800 \
    "${BASE_URL}/${file}?download=true" -o "${TMP_DIR}/${file}"
  [[ -s "${TMP_DIR}/${file}" ]]
done

if [[ $(stat -c%s "${TMP_DIR}/model.bin") -le 300000000 ]]; then
  echo "Downloaded model.bin is unexpectedly small; refusing install." >&2
  exit 1
fi

rm -rf "${MODEL_DIR}"
mv "${TMP_DIR}" "${MODEL_DIR}"
trap - EXIT
chown -R bikhabar:bikhabar "${MODEL_DIR}"
chmod 750 "${MODEL_DIR}"
find "${MODEL_DIR}" -type f -exec chmod 640 {} +
echo "OFFLINE_TRANSLATOR=installed path=${MODEL_DIR}"
