#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$PROJECT_DIR/backend/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Ask Katy's backend virtual environment is missing. Run the local setup first." >&2
  exit 1
fi

exec "$PYTHON" "$PROJECT_DIR/scripts/deploy.py" "$@"
