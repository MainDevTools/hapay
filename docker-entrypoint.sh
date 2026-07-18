#!/bin/sh
# Один образ — три ролі (api / migrate / collect). Роль задає команда в compose.
set -e

if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "▶ applying migrations…"
  python -m db.migrate
fi

# Явна команда (напр. `python -m db.migrate` або `python -m collect`) — виконати ЇЇ.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# Без команди — дефолт: read-API.
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8080}"
