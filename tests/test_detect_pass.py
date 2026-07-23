"""Інтеграційний тест detect_pass проти живого Timescale (§5/§8.4). Skip-aware (CI).

Сіє синтетичну історію (30 днів по 100 грн + поточна 80), ганяє detect_pass,
перевіряє зелений бейдж + ідемпотентність (announce заморожено, без дублів).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.dbguard import reset, test_dsn         # noqa: E402
URL = test_dsn("test_detect_pass")                # РУЙНІВНИЙ: нижче reset() дропає все

import psycopg                                    # noqa: E402
from db import migrate                            # noqa: E402
from db.store import upsert_source                # noqa: E402
from detection.runner import detect_pass, close_absent  # noqa: E402


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

        # закриття зниклих (§5.5): товар, чиї снапшоти старші за grace, → ended_at
        gone = conn.execute(
            "INSERT INTO store_product (source_id, external_ref, url, title, category_id) "
            "VALUES (%s,'gone#v=1','https://test.example/gone','Зниклий',%s) RETURNING store_product_id",
            (sid, cat)).fetchone()[0]
        conn.execute(
            "INSERT INTO price_snapshot (store_product_id, price_now_kop, price_old_kop, in_stock, source_method, seen_at) "
            "VALUES (%s, 5000, 6000, true, 'test', now() - make_interval(hours => 40))", (gone,))
        detect_pass(conn)                                   # заведе declared-подію для зниклого
        closed = close_absent(conn, grace_hours=26)
        checks.append(("close_absent закрив ≥1", closed >= 1, closed))
        gone_closed = conn.execute("SELECT ended_at IS NOT NULL FROM discount_event "
                                   "WHERE store_product_id=%s", (gone,)).fetchone()
        checks.append(("зниклий товар закрито", gone_closed == (True,), gone_closed))
        fresh_open = conn.execute("SELECT count(*) FROM discount_event "
                                  "WHERE store_product_id=%s AND ended_at IS NULL", (spid,)).fetchone()[0]
        checks.append(("свіжий товар лишився відкритим", fresh_open == 1, fresh_open))

        # серіалізація (2026-07-23): паралельні detect_pass билися за лок discount_event
        # (LockNotAvailable → 500 на ingest). Тепер другий одночасний прохід пропускає
        # (None), а після відпускання лока все працює як раніше. Session- і xact-advisory
        # локи живуть в одному просторі — тримаємо session-лок з другого конекшена.
        with psycopg.connect(URL, autocommit=True) as rival:
            rival.execute("SELECT pg_advisory_lock(hashtext('detect_pass'))")
            skipped = detect_pass(conn)
            checks.append(("зайнятий advisory-лок → прохід пропущено (None)",
                           skipped is None, skipped))
            rival.execute("SELECT pg_advisory_unlock(hashtext('detect_pass'))")
        again = detect_pass(conn)
        checks.append(("після відпускання лока прохід знову рахує (int)",
                       isinstance(again, int), again))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
