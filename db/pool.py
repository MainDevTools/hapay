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

_pool: ConnectionPool | None = None


def _configure(conn) -> None:
    """Таймаути per-connection (аналог інваріанта 11). Через `SET`, а НЕ startup-`options`:
    PgBouncer-пулер Neon (`-pooler`) не приймає `options` → конект висне. Best-effort."""
    try:
        conn.execute("SET statement_timeout = '30s'")
        conn.execute("SET lock_timeout = '10s'")
        conn.commit()
    except Exception:
        pass


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
                               configure=_configure)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
