"""Форвардний міграційний раннер (§6.6): застосовує migrations/NNNN_*.sql, трек у schema_migration.

Скрипт кожної міграції виконується як ОДИН simple-query (libpq `PQexec` через
`pgconn.exec_`) — це коректно ганяє багатостейтментний файл із `$$`-тілами й
дозволяє Timescale-оператори, які НЕ можна в явній транзакції
(`CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)`).
"""
from __future__ import annotations
import os
import glob
import psycopg
from psycopg import pq
from .pool import dsn

MIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")

_OK = {pq.ExecStatus.COMMAND_OK, pq.ExecStatus.TUPLES_OK}


def pending() -> list[tuple[int, str]]:
    files = sorted(glob.glob(os.path.join(MIG_DIR, "[0-9][0-9][0-9][0-9]_*.sql")))
    return [(int(os.path.basename(f)[:4]), f) for f in files]


def _applied(conn) -> set[int]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migration "
                 "(version INT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    return {r[0] for r in conn.execute("SELECT version FROM schema_migration").fetchall()}


def apply(url: str | None = None) -> list[int]:
    """Застосувати всі pending-міграції. Повертає список застосованих версій."""
    url = url or dsn()
    applied: list[int] = []
    with psycopg.connect(url, autocommit=True) as conn:
        done = _applied(conn)
        for version, path in pending():
            if version in done:
                continue
            sql = open(path, encoding="utf-8").read()
            res = conn.pgconn.exec_(sql.encode("utf-8"))       # simple protocol, multi-statement
            if res.status not in _OK:
                msg = (res.error_message or b"").decode("utf-8", "replace")
                raise RuntimeError(f"міграція {version} впала: {msg}")
            conn.execute("INSERT INTO schema_migration(version) VALUES (%s)", (version,))
            applied.append(version)
    return applied


if __name__ == "__main__":
    print("застосовано:", apply())
