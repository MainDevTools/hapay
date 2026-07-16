"""Інтеграційний тест detect_pass проти живого Timescale (§5/§8.4). Skip-aware (CI).

Сіє синтетичну історію (30 днів по 100 грн + поточна 80), ганяє detect_pass,
перевіряє зелений бейдж + ідемпотентність (announce заморожено, без дублів).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

URL = os.environ.get("DATABASE_URL")
if not URL:
    print("SKIP test_detect_pass: DATABASE_URL не задано.")
    sys.exit(0)

import psycopg                                    # noqa: E402
from db import migrate                            # noqa: E402
from db.store import upsert_source                # noqa: E402
from detection.runner import detect_pass          # noqa: E402
from tests.test_migration import reset            # noqa: E402  (перевикористовуємо teardown)


def main():
    with psycopg.connect(URL, autocommit=True) as conn:
        reset(conn)
    migrate.apply(URL)

    checks, failed = [], 0
    with psycopg.connect(URL, autocommit=True) as conn:
        cat = conn.execute("SELECT category_id FROM category WHERE slug='uncategorized'").fetchone()[0]
        sid = upsert_source(conn, "TestStore", "https://test.example", adapter_kind="ssr")
        spid = conn.execute(
            "INSERT INTO store_product (source_id, external_ref, url, title, category_id) "
            "VALUES (%s,'korm#v=1','https://test.example/korm','Тест корм',%s) RETURNING store_product_id",
            (sid, cat)).fetchone()[0]

        # 30 днів по 10000 коп (100 грн), потім поточна 8000 (80 грн) сьогодні
        for i in range(1, 31):
            conn.execute(
                "INSERT INTO price_snapshot (store_product_id, price_now_kop, in_stock, source_method, seen_at) "
                "VALUES (%s, 10000, true, 'test', now() - make_interval(days => %s))", (spid, i))
        conn.execute(
            "INSERT INTO price_snapshot (store_product_id, price_now_kop, in_stock, source_method, seen_at) "
            "VALUES (%s, 8000, true, 'test', now())", (spid,))

        n = detect_pass(conn)
        checks.append(("detect_pass upsert-нув подію", n >= 1, n))

        ev = conn.execute(
            "SELECT badge_state, reference_kop, verified_pct FROM discount_event "
            "WHERE store_product_id=%s", (spid,)).fetchone()
        checks.append(("бейдж verified, ref=10000, −20%", ev == ("verified", 10000, 20), ev))

        # ідемпотентність: повторний прохід не плодить дублів, announce заморожено (§8.4)
        detect_pass(conn)
        cnt = conn.execute("SELECT count(*) FROM discount_event WHERE store_product_id=%s", (spid,)).fetchone()[0]
        checks.append(("повторний detect_pass без дублів", cnt == 1, cnt))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
