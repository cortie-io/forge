#!/usr/bin/env sh
set -eu

uvicorn app.main:app --host 0.0.0.0 --port "${PY_API_PORT:-8000}" --proxy-headers
