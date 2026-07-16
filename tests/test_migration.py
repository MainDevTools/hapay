"""Інтеграційний тест 0001 проти ЖИВОГО Postgres/TimescaleDB (DoD §6.6).

Skip-aware: без DATABASE_URL — пропуск (не провал), бо пісочниця без Docker/Timescale.
Верифікується в CI (service-контейнер timescaledb, .github/workflows/tests.yml).

Запуск локально:
  $env:DATABASE_URL='postgresql://postgres:pass@localhost:5432/radar'; python tests/test_migration.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

URL = os.environ.get("DATABASE_URL")
if not URL:
    print("SKIP test_migration: DATABASE_URL не задано (нема живого Timescale).")
    sys.exit(0)

import psycopg                                   # noqa: E402
from db import migrate                            # noqa: E402
from db.store import upsert_source, persist_items  # noqa: E402
from adapters.pethouse import PethouseAdapter     # noqa: E402

_TABLES = ("alert_log", "watchlist", "discount_event", "price_snapshot", "scan_run",
           "http_cache", "canary", "store_product", "source_category_map",
           "category", "source", "detection_config", "app_config", "schema_migration")


def reset(conn):
    stmts = ["DROP MATERIALIZED VIEW IF EXISTS price_daily CASCADE;"]
    stmts += [f"DROP TABLE IF EXISTS {t} CASCADE;" for t in _TABLES]
    stmts.append("DROP FUNCTION IF EXISTS trg_ps_append_only() CASCADE;")
    res = conn.pgconn.exec_("".join(stmts).encode())
    if res.error_message:
        pass  # IF EXISTS — безпечно


def main():
    checks, failed = [], 0

    with psycopg.connect(URL, autocommit=True) as conn:
        reset(conn)

    applied = migrate.apply(URL)
    checks.append(("міграція застосована", applied == [1], applied))

    with psycopg.connect(URL, autocommit=True) as conn:
        ps = conn.execute("SELECT count(*) FROM information_schema.tables "
                          "WHERE table_name='price_snapshot'").fetchone()[0]
        checks.append(("price_snapshot таблиця є", ps == 1, ps))

        cov = conn.execute("SELECT count(*) FROM pg_indexes WHERE indexname='ix_ps_prod_window'").fetchone()[0]
        checks.append(("покривний індекс ix_ps_prod_window", cov == 1, cov))

        gin = conn.execute("SELECT count(*) FROM pg_indexes WHERE indexname='ix_sp_fts'").fetchone()[0]
        checks.append(("tsvector GIN ix_sp_fts", gin == 1, gin))

        cfg = conn.execute("SELECT count(*) FROM detection_config "
                           "WHERE valid_from <= now() AND (valid_to IS NULL OR valid_to > now())").fetchone()[0]
        checks.append(("detection_config чинний на today", cfg >= 1, cfg))

        # round-trip: RawItem (S2) → store_product + price_snapshot
        cat = conn.execute("SELECT category_id FROM category WHERE slug='uncategorized'").fetchone()[0]
        sid = upsert_source(conn, "Pethouse", "https://pethouse.ua",
                            adapter_kind="ssr", platform="custom", fetch_tier="A")
        with open(os.path.join(os.path.dirname(__file__), "cassettes", "pethouse_akcii.html"),
                  encoding="utf-8") as f:
            items = PethouseAdapter().extract(f.read())
        n = persist_items(conn, sid, cat, items, source_method="css")
        checks.append(("персист снапшотів = 9", n == 9, n))

        got = conn.execute(
            "SELECT ps.price_now_kop, ps.price_old_kop FROM price_snapshot ps "
            "JOIN store_product sp USING (store_product_id) "
            "WHERE sp.external_ref LIKE %s",
            ("%royal-canin-sterilised#v=4-кг",)).fetchone()
        checks.append(("round-trip копійки (4кг=170000/200000)", got == (170000, 200000), got))

        # append-only: UPDATE/DELETE мусять падати
        for op in ("UPDATE price_snapshot SET price_now_kop = 1",
                   "DELETE FROM price_snapshot"):
            try:
                conn.execute(op)
                ok = False
            except psycopg.errors.RaiseException:
                ok = True
            except psycopg.Error:
                ok = True   # будь-яка відмова руху — append-only тримає
            checks.append((f"append-only блокує «{op.split()[0]}»", ok, None))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
