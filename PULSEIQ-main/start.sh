#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt -r requirements-connectors.txt
exec .venv/bin/python -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port "${PORT:-8000}"
