#!/bin/sh
# Старт read-API. RUN_MIGRATIONS=1 → застосувати 0001 перед стартом (зручно на першому деплої).
set -e

if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "▶ applying migrations…"
  python -m db.migrate
fi

exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8080}"
