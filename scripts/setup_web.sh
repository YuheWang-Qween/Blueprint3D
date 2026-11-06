#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
if [ -n "${PIP_TARGET:-}" ]; then
  python3 -m pip install --disable-pip-version-check --target "$PIP_TARGET" -r requirements.txt
  export PYTHONPATH="$PIP_TARGET${PYTHONPATH:+:$PYTHONPATH}"
  BLUEPRINT_PYTHON=python3
else
  python3 -m venv .venv
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
  BLUEPRINT_PYTHON=.venv/bin/python
fi
test -s webapp/static/viewer.bundle.js
"$BLUEPRINT_PYTHON" -c 'import fastapi, uvicorn, cv2, trimesh, shapely, manifold3d'
