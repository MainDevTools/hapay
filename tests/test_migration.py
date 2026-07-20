"""Інтеграційний тест 0001 проти ЖИВОГО Postgres (DoD §6.6).

Skip-aware: без TEST_DATABASE_URL — пропуск (не провал), бо пісочниця без Docker.
Верифікується в CI (service-контейнер postgres, .github/workflows/tests.yml).

Запуск локально (ОКРЕМА тестова база, не прод!):
  $env:TEST_DATABASE_URL='postgresql://postgres:pass@localhost:5432/radar_test'
  python tests/test_migration.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.dbguard import reset, test_dsn, _TABLES  # noqa: E402,F401  (reset реекспорт — сумісність)

URL = test_dsn("test_migration")

import psycopg                                   # noqa: E402
from db import migrate                            # noqa: E402
from db.store import upsert_source, persist_items, load_categories  # noqa: E402
from adapters.pethouse import PethouseAdapter     # noqa: E402


def main():
    checks, failed = [], 0

    with psycopg.connect(URL, autocommit=True) as conn:
        reset(conn)

    applied = migrate.apply(URL)
    checks.append(("міграції застосовані (0001…0007)", applied == [1, 2, 3, 4, 5, 6, 7], applied))

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
        cats = load_categories(conn)
        sid = upsert_source(conn, "Pethouse", "https://pethouse.ua",
                            adapter_kind="ssr", platform="custom", fetch_tier="A")
        with open(os.path.join(os.path.dirname(__file__), "cassettes", "pethouse_akcii.html"),
                  encoding="utf-8") as f:
            items = PethouseAdapter().extract(f.read())
        n = persist_items(conn, sid, items, cats, source_method="css")
        checks.append(("персист снапшотів = 9", n == 9, n))

        cat_ok = conn.execute("SELECT c.slug FROM store_product sp JOIN category c USING (category_id) "
                              "WHERE sp.external_ref LIKE '%royal-canin-sterilised%' LIMIT 1").fetchone()
        checks.append(("категорія за URL = koty-suhyi-korm", cat_ok == ("koty-suhyi-korm",), cat_ok))

        # category_slug (з лістинга) перебиває categorize() — товар з зоо-URL, але тег «smartfony».
        # Окреме джерело, щоб не чіпати попередній round-trip (UNIQUE source_id+external_ref).
        sid2 = upsert_source(conn, "Foxtrot", "https://www.foxtrot.com.ua",
                             adapter_kind="ssr", platform="custom", fetch_tier="A")
        persist_items(conn, sid2, items, cats, source_method="css", category_slug="smartfony")
        ov = conn.execute("SELECT c.slug FROM store_product sp JOIN category c USING (category_id) "
                          "WHERE sp.source_id = %s LIMIT 1", (sid2,)).fetchone()
        checks.append(("category_slug перебиває URL = smartfony", ov == ("smartfony",), ov))

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
