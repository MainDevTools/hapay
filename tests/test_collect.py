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

    def _read(name):
        with open(os.path.join(os.path.dirname(__file__), "cassettes", name), encoding="utf-8") as f:
            return f.read()
    cas_ph, cas_pc = _read("pethouse_akcii.html"), _read("petchoice_akcii.html")
    fetch = lambda url: cas_pc if "petchoice" in url else cas_ph   # DI: касета за URL, без HTTP

    checks, failed = [], 0
    with psycopg.connect(URL, autocommit=True) as conn:
        stats = collect(conn, SOURCES, fetch=fetch, delay=0)
        checks.append(("collect items = 12 (Pethouse 9 dedup + PetChoice 3)", stats["items"] == 12, stats))

        snaps = conn.execute("SELECT count(*) FROM price_snapshot").fetchone()[0]
        checks.append(("price_snapshot = 12", snaps == 12, snaps))

        sr = conn.execute("SELECT count(*), count(*) FILTER (WHERE surface='discovery') FROM scan_run").fetchone()
        checks.append(("2 discovery scan_run", sr == (2, 2), sr))

        ev = conn.execute("SELECT count(*), count(*) FILTER (WHERE badge_state='declared') "
                          "FROM discount_event").fetchone()
        checks.append(("11 подій, усі declared (8 PH + 3 PC)", ev == (11, 11), ev))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
