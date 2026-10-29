#!/usr/bin/env sh
set -eu
TASK_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ ! -x "$TASK_DIR/.venv/bin/python" ]; then
  echo 'Please run ./setup.sh --web first.'
  exit 2
fi
exec "$TASK_DIR/.venv/bin/python" "$TASK_DIR/web.py" --allow-live "$@"
