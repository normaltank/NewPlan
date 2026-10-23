#!/usr/bin/env bash
# First use: bash install-linux.sh. Later: bash run.sh.
set -euo pipefail
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec bash ./run.sh "$@"
