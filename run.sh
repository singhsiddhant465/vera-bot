#!/usr/bin/env bash
set -euo pipefail
# Local run helper. Override PORT via env if needed.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
