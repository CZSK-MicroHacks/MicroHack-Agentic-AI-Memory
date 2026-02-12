#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST="${1:-}"

if [[ -z "${DEST}" ]]; then
  echo "Usage: $(basename "$0") <destination-path>"
  exit 1
fi

mkdir -p "${DEST}"

rsync -a --filter=':- .gitignore' "${PROJECT_ROOT}/" "${DEST}/"

echo "Copied ${PROJECT_ROOT} to ${DEST}"
