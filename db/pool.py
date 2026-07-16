"""З'єднання з central PostgreSQL/TimescaleDB (§6/§8.10.1).

`DATABASE_URL` — ЛИШЕ з середовища (секрет; ніколи в репо/логах — git-безпека §8).
Пул із `statement_timeout`/`lock_timeout` (аналог інваріанта 11 для Postgres).
"""
from __future__ import annotations
import os
from psycopg_pool import ConnectionPool

# Локальний .env (gitignored) → DATABASE_URL без ручного env щоразу.
# У CI/проді змінна вже в середовищі → load_dotenv її НЕ перезаписує (no-op).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# server-side таймаути на кожне з'єднання (мс)
_CONN_OPTS = "-c statement_timeout=30000 -c lock_timeout=10000"

_pool: ConnectionPool | None = None


def dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL не задано. Постав у середовищі (не в репо!): "
            "$env:DATABASE_URL='postgresql://user:pass@host:5432/radar'"
        )
    return url


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(dsn(), min_size=1, max_size=8, open=True,
                               kwargs={"options": _CONN_OPTS})
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
