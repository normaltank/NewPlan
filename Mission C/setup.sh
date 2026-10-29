#!/usr/bin/env bash
set -euo pipefail
mission_c_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mission_c_bootstrap="${MISSION_C_PYTHON:-python3}"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != '--web' && "$1" != '--full' ) ]]; then
  echo 'Usage: ./setup.sh [--web|--full]' >&2
  exit 2
fi
if [[ ! -x "$mission_c_dir/.venv/bin/python" ]]; then
  "$mission_c_bootstrap" -m venv "$mission_c_dir/.venv"
fi
mission_c_python="$mission_c_dir/.venv/bin/python"
"$mission_c_python" -m pip install -r "$mission_c_dir/requirements.txt"
if [[ "${1:-}" == '--web' || "${1:-}" == '--full' ]]; then
  "$mission_c_python" -m pip install -r "$mission_c_dir/requirements-web.txt"
fi
if [[ "${1:-}" == '--full' ]]; then
  "$mission_c_python" -m pip install -r "$mission_c_dir/requirements-browser.txt" -r "$mission_c_dir/requirements-ocr.txt"
  "$mission_c_python" -m playwright install chromium
fi
echo 'Mission C is ready. See SERVER.md for scan/worker/watch and BATCH.md for the offline demo.'
