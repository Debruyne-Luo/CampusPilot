#!/usr/bin/env bash
# One-time (and after dependency changes): shared venv at /opt/campuspilot/venv with Python 3.14.
# The campuspilot package itself is NOT installed; releases are loaded via PYTHONPATH from
# /opt/campuspilot/current/backend/src, so switching `current` switches code atomically.
# Run as root. Pass --vector to install the optional sqlite-vec/numpy backend.
set -euo pipefail
PY=${PYTHON:-/usr/local/bin/python3.14}
VENV=/opt/campuspilot/venv
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install 'fastapi>=0.135,<1' 'uvicorn>=0.34,<1' 'httpx>=0.28,<1' 'pydantic>=2.12,<3' 'pillow>=12,<13'
if [ "${1:-}" = "--vector" ]; then
  # Optional; without it retrieval uses the pure-Python cosine fallback (same results, slower).
  "$VENV/bin/pip" install 'sqlite-vec>=0.1.6,<0.2' 'numpy>=2,<3'
fi
chown -R root:root "$VENV"
"$VENV/bin/python" -c "import fastapi, uvicorn, httpx, PIL; print('deps ok')"
