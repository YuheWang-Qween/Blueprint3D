#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
if [ -d .web-deps ]; then
  export PYTHONPATH="$PWD/.web-deps${PYTHONPATH:+:$PYTHONPATH}"
fi
if [ -z "${BLUEPRINT_PYTHON:-}" ]; then
  if [ -d .web-deps ]; then BLUEPRINT_PYTHON=python3
  elif [ -x .venv/bin/python ]; then BLUEPRINT_PYTHON=.venv/bin/python
  else BLUEPRINT_PYTHON=python3; fi
fi
BLUEPRINT_PORT="${DEPLOY_RUN_PORT:-${PORT:-5000}}"
exec "$BLUEPRINT_PYTHON" -m uvicorn webapp.app:app --host 0.0.0.0 --port "$BLUEPRINT_PORT" --workers 1
