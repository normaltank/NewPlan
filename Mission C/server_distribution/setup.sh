#!/usr/bin/env bash
set -euo pipefail
mission_c_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mission_c_bootstrap="${MISSION_C_PYTHON:-python3}"
if [[ ! -x "$mission_c_dir/.venv/bin/python" ]]; then
  "$mission_c_bootstrap" -m venv "$mission_c_dir/.venv"
fi
"$mission_c_dir/.venv/bin/python" -m pip install -r "$mission_c_dir/requirements.txt"
mkdir -p "$mission_c_dir/input"
echo 'Ready. Run ./start.sh demo, then ./start.sh preview or ./start.sh watch. See README.md.'
