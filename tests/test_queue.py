"""Тест черги-оренди (T16, крок 1) проти живого Postgres. Руйнівний → dbguard (T13).

Час не чекаємо — зсуваємо not_before/leased_until напряму SQL-ом (детерміновано).

Запуск:  python tests/test_queue.py   (потрібен TEST_DATABASE_URL)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.dbguard import reset, test_dsn               # noqa: E402
URL = test_dsn("test_queue")

import psycopg                                          # noqa: E402
from db import migrate                                  # noqa: E402
from api import qtasks                                  # noqa: E402


def main():
    checks, failed = [], 0
    with psycopg.connect(URL, autocommit=True) as conn:
        reset(conn)
    migrate.apply(URL)

    with psycopg.connect(URL, autocommit=True) as conn:
        # ── сів: HTML_SOURCES → задачі; повторний сів нічого не дублює ────────────
        n1 = qtasks.seed_tasks(conn)
        n2 = qtasks.seed_tasks(conn)
        checks.append(("сів створює задачі (Allo hub + Fox + Moyo)", n1 >= 3, n1))
        checks.append(("повторний сів ідемпотентний (0 нових)", n2 == 0, n2))

        # друга задача Allo — щоб розліт було ВИДНО (вільна задача source ≠ доступна)
        conn.execute("INSERT INTO collect_task (source, url, kind) VALUES "
                     "('Allo', 'https://allo.ua/ua/events-and-discounts/extra-action/', 'page')")

        # ── оренда: по ОДНІЙ задачі на крамницю, навіть якщо limit більший ────────
        got = qtasks.lease_tasks(conn, "phone-A", limit=5)
        srcs = [t["source"] for t in got]
        checks.append(("оренда віддає по 1 на крамницю", len(srcs) == len(set(srcs)), srcs))
        checks.append(("усі 3 крамниці в першій оренді", len(got) == 3, len(got)))

        # ── розліт 15 хв: друга задача Allo ВІЛЬНА, але not_before зсунуто ────────
        got_b = qtasks.lease_tasks(conn, "phone-B", limit=5)
        checks.append(("другий телефон одразу → порожньо (розліт, не зайнятість)",
                       got_b == [], got_b))

        # ── закриття: not_before стрибає на repeat_min; чужий не закриє ───────────
        t0 = got[0]
        checks.append(("чужий worker не закриє задачу",
                       qtasks.complete_task(conn, t0["task_id"], "phone-B", ok=True) is False, None))
        checks.append(("свій worker закриває",
                       qtasks.complete_task(conn, t0["task_id"], "phone-A", ok=True) is True, None))
        row = conn.execute("SELECT last_status, fail_count, "
                           "not_before > now() + interval '11 hours' AS far "
                           "FROM collect_task WHERE task_id=%s", (t0["task_id"],)).fetchone()
        checks.append(("успіх: status=ok, наступний прохід ~repeat_min",
                       row[0] == "ok" and row[1] == 0 and row[2], row))

        # ── збій: бекоф росте, fail_count лічить ──────────────────────────────────
        t1 = got[1]
        qtasks.complete_task(conn, t1["task_id"], "phone-A", ok=False, note="HTTP 403")
        row = conn.execute("SELECT last_status, fail_count FROM collect_task WHERE task_id=%s",
                           (t1["task_id"],)).fetchone()
        checks.append(("збій: fail:HTTP 403, fail_count=1",
                       row[0] == "fail:HTTP 403" and row[1] == 1, row))

        # ── протухла оренда повертає задачу в чергу ───────────────────────────────
        t2 = got[2]
        conn.execute("UPDATE collect_task SET leased_until = now() - interval '1 minute', "
                     "not_before = now() - interval '1 minute' WHERE task_id=%s", (t2["task_id"],))
        got_c = qtasks.lease_tasks(conn, "phone-C", limit=5)
        checks.append(("протухла оренда → задачу бере інший телефон",
                       any(t["task_id"] == t2["task_id"] for t in got_c), got_c))

        # ── дозрівання: зсуваємо час у минуле → задачі знову дозріли ──────────────
        conn.execute("UPDATE collect_task SET not_before = now() - interval '1 minute', "
                     "leased_until = NULL")
        got_d = qtasks.lease_tasks(conn, "phone-D", limit=2)
        checks.append(("limit=2 ріже видачу (навіть якщо дозріло 3+)", len(got_d) == 2, len(got_d)))

        # ── enqueue_pages: лендинги хаба → у чергу, ідемпотентно, з розльотом ─────
        urls = ["https://allo.ua/ua/events-and-discounts/aaa-action/",
                "https://allo.ua/ua/events-and-discounts/bbb-action/"]
        e1 = qtasks.enqueue_pages(conn, "Allo", urls)
        e2 = qtasks.enqueue_pages(conn, "Allo", urls)
        checks.append(("лендинги в черзі (2 нові, повтор 0)", e1 == 2 and e2 == 0, (e1, e2)))
        nb = conn.execute("SELECT count(*) FROM collect_task WHERE source='Allo' "
                          "AND kind='page' AND not_before > now()").fetchone()[0]
        checks.append(("лендинги з розльотом (not_before у майбутньому)", nb >= 2, nb))

        # ── stats: зріз по крамницях ──────────────────────────────────────────────
        st = qtasks.queue_stats(conn)
        checks.append(("stats: є всі 3 крамниці",
                       {s["source"] for s in st} >= {"Allo", "Foxtrot", "Moyo"},
                       [s["source"] for s in st]))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
