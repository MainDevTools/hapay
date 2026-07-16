"""Інтеграційний тест колектора проти живого Timescale (§8.1). Skip-aware (CI).

Детерміновано: fetch підмінено на КАСЕТУ Pethouse (без живого HTTP). Перевіряє
повний конвеєр fetch→extract→persist→detect_pass: 9 снапшотів + scan_run +
declared-події (одиночний прогін = ще без 30-денної історії).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

URL = os.environ.get("DATABASE_URL")
if not URL:
    print("SKIP test_collect: DATABASE_URL не задано.")
    sys.exit(0)

import psycopg                                    # noqa: E402
from db import migrate                            # noqa: E402
from collect import collect, SOURCES              # noqa: E402
from tests.test_migration import reset            # noqa: E402


def main():
    with psycopg.connect(URL, autocommit=True) as conn:
        reset(conn)
    migrate.apply(URL)

    with open(os.path.join(os.path.dirname(__file__), "cassettes", "pethouse_akcii.html"),
              encoding="utf-8") as f:
        cassette = f.read()

    checks, failed = [], 0
    with psycopg.connect(URL, autocommit=True) as conn:
        stats = collect(conn, SOURCES, fetch=lambda url: cassette)   # DI: касета замість HTTP
        checks.append(("collect items = 9", stats["items"] == 9, stats))

        snaps = conn.execute("SELECT count(*) FROM price_snapshot").fetchone()[0]
        checks.append(("price_snapshot = 9", snaps == 9, snaps))

        sr = conn.execute("SELECT surface, items_seen FROM scan_run "
                          "ORDER BY scan_run_id DESC LIMIT 1").fetchone()
        checks.append(("scan_run discovery, items_seen=9", sr == ("discovery", 9), sr))

        ev = conn.execute("SELECT count(*), count(*) FILTER (WHERE badge_state='declared') "
                          "FROM discount_event").fetchone()
        checks.append(("8 подій, усі declared (одиночний прогін)", ev == (8, 8), ev))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
