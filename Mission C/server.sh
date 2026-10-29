#!/usr/bin/env bash
set -euo pipefail
mission_c_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mission_c_python="${MISSION_C_PYTHON:-$mission_c_dir/.venv/bin/python}"
if [[ ! -x "$mission_c_python" ]]; then
  echo 'Run ./setup.sh first or set MISSION_C_PYTHON to a prepared Python executable. See SERVER.md.' >&2
  exit 2
fi
export PYTHONUTF8=1
exec "$mission_c_python" "$mission_c_dir/server.py" "$@"
