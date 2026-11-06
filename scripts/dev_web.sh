#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Coze's preview runner executes dev.run directly; dev.build is not an install hook.
bash "$SCRIPT_DIR/setup_web.sh"
exec bash "$SCRIPT_DIR/start_web.sh"
