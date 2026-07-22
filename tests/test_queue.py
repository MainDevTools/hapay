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
from api.ingest import HTML_SOURCES                     # noqa: E402

N_SRC = len(HTML_SOURCES)                               # к-сть крамниць у черзі (росте з адаптерами)
PER_LEASE = min(N_SRC, qtasks.MAX_LEASE)               # одна оренда — не більше стелі MAX_LEASE


def main():
    checks, failed = [], 0
    with psycopg.connect(URL, autocommit=True) as conn:
        reset(conn)
    migrate.apply(URL)

    with psycopg.connect(URL, autocommit=True) as conn:
        # ── сів: HTML_SOURCES → задачі; повторний сів нічого не дублює ────────────
        n1 = qtasks.seed_tasks(conn)
        n2 = qtasks.seed_tasks(conn)
        checks.append((f"сів створює задачі (≥{N_SRC} крамниць HTML_SOURCES)", n1 >= N_SRC, n1))
        checks.append(("повторний сів ідемпотентний (0 нових)", n2 == 0, n2))

        # ── сів прибирає задачі, які ВИБУЛИ з конфігу ─────────────────────────────
        # Заміряно на проді 2026-07-21: 12 задач Eldorado виду `.../page=2/` жили від
        # старого конфігу з пагінацією. Вони віддавали ПЕРШУ сторінку й ставили `ok`,
        # тобто ми двічі на добу качали ту саму сторінку дванадцять разів, а черга
        # виглядала абсолютно здоровою.
        conn.execute("INSERT INTO collect_task (source, url, kind, priority) VALUES "
                     "('Eldorado', 'https://eldorado.ua/uk/led/c1038962/page=9/', 'page', 100)")
        # а це — лендинг, знайдений хабом: у конфізі його НЕМА за визначенням
        conn.execute("INSERT INTO collect_task (source, url, kind, priority) VALUES "
                     "('Allo', 'https://allo.ua/ua/events-and-discounts/test-action/', 'page', 50)")
        qtasks.seed_tasks(conn)
        # точний URL, а не LIKE: `page=9` є в КОНФІЗІ у Rozetka та інших (pages=10),
        # і широкий шаблон ловив законні задачі — тест падав на 14 замість 0
        ghost = conn.execute(
            "SELECT count(*) FROM collect_task WHERE url = %s",
            ("https://eldorado.ua/uk/led/c1038962/page=9/",)).fetchone()[0]
        found = conn.execute("SELECT count(*) FROM collect_task WHERE url LIKE '%test-action%'").fetchone()[0]
        checks.append(("сів прибирає задачу, якої вже нема в конфігу", ghost == 0, ghost))
        checks.append(("лендинг із hub-discovery сів НЕ чіпає (priority=50)", found == 1, found))
        # ПРИБИРАЄМО ЗА СОБОЮ: задача з priority=50 стає першою в оренді (сортування
        # priority, not_before) і ламає перевірку чесної ротації нижче. Двічі за сесію
        # наступив на це — фікстур, що переживає свою перевірку, псує сусідні.
        conn.execute("DELETE FROM collect_task WHERE url LIKE '%test-action%'")

        # ── періодичність за глибиною: перші сторінки частіше, хвіст рідше ────────
        # Заміряно на проді 2026-07-21: колектор дає ~480 запусків на добу, а рівний
        # розклад 720 хв на всі задачі вимагав 496 — впритул до стелі, 43 задачі були
        # прострочені. Розведення знижує потребу до ~293, тобто дає запас ≈1.6×.
        deep = conn.execute(
            "SELECT count(*) FROM collect_task WHERE repeat_min = %s",
            (qtasks.DEEP_REPEAT_MIN,)).fetchone()[0]
        shallow = conn.execute(
            "SELECT count(*) FROM collect_task WHERE repeat_min = %s",
            (qtasks.PAGE_REPEAT_MIN,)).fetchone()[0]
        checks.append(("глибокі сторінки мають рідший розклад", deep > 0, deep))
        checks.append(("перші сторінки лишились частими", shallow > 0, shallow))
        checks.append(("сторінка 1 — частий розклад, 10 — рідкий",
                       qtasks.repeat_for_page(1) == qtasks.PAGE_REPEAT_MIN
                       and qtasks.repeat_for_page(10) == qtasks.DEEP_REPEAT_MIN,
                       (qtasks.repeat_for_page(1), qtasks.repeat_for_page(10))))

        # ПОЛІТИКА застосовується й до ВЖЕ наявних задач: інакше зміна періодичності
        # діяла б лише на нові, і черга жила б за двома розкладами водночас.
        conn.execute("UPDATE collect_task SET repeat_min = 999 WHERE repeat_min = %s",
                     (qtasks.DEEP_REPEAT_MIN,))
        qtasks.seed_tasks(conn)
        stale = conn.execute("SELECT count(*) FROM collect_task WHERE repeat_min = 999").fetchone()[0]
        checks.append(("сів виправляє розклад наявних задач", stale == 0, stale))

        # друга задача Allo — щоб розліт було ВИДНО (вільна задача source ≠ доступна)
        conn.execute("INSERT INTO collect_task (source, url, kind) VALUES "
                     "('Allo', 'https://allo.ua/ua/events-and-discounts/extra-action/', 'page')")

        # ── оренда: по ОДНІЙ задачі на крамницю, навіть якщо limit більший ────────
        got = qtasks.lease_tasks(conn, "phone-A", limit=N_SRC + 3)
        srcs = [t["source"] for t in got]
        checks.append(("оренда віддає по 1 на крамницю", len(srcs) == len(set(srcs)), srcs))
        checks.append((f"перша оренда = min(джерел, стеля) = {PER_LEASE}", len(got) == PER_LEASE, len(got)))

        # ── розліт 15 хв: жодна ЩОЙНО орендована крамниця недоступна другому телефону
        # (навіть якщо в неї лишились вільні задачі, як 2-га Allo) ────────────────
        got_b = qtasks.lease_tasks(conn, "phone-B", limit=N_SRC + 3)
        leased_srcs = {t["source"] for t in got}
        checks.append(("розліт: орендовані крамниці недоступні другому телефону",
                       {t["source"] for t in got_b}.isdisjoint(leased_srcs), got_b))

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

        # ── чесна ротація (антистарвейшн): усі дозрілі, але 3 крамниці «свіжі», 3 «древні»
        # → оренда бере ДРЕВНІ, а не перші за абеткою (інакше нові адаптери голодували б)
        conn.execute("UPDATE collect_task SET leased_until = NULL, not_before = now() - interval '1 hour'")
        srcs = [r[0] for r in conn.execute("SELECT DISTINCT source FROM collect_task "
                                           "ORDER BY source").fetchall()]
        if len(srcs) >= 4:
            fresh = srcs[:len(srcs) // 2]      # перші за абеткою — робимо СВІЖИМИ (щойно збирані)
            conn.execute("UPDATE collect_task SET not_before = now() - interval '1 minute' "
                         "WHERE source = ANY(%s)", (fresh,))
            got_fair = qtasks.lease_tasks(conn, "phone-fair", limit=len(fresh))
            picked = {t["source"] for t in got_fair}
            checks.append(("чесна ротація: бере найдовше очікувані, не за абеткою",
                           bool(picked) and picked.isdisjoint(set(fresh)), (sorted(picked), fresh)))

        # ── фільтр за режимом (PC-колектор, T-reliab): modes=['fetch'] не віддає render ──
        # PC збирає лише fetch-крамниці зі свого IP; render (Comfy/Brain/…) лишається
        # телефону. Так два робітники ділять чергу за здатністю, не крадучи задач.
        from api.ingest import COLLECT_MODE
        render_srcs = {s for s, m in COLLECT_MODE.items() if m == "render"}
        conn.execute("UPDATE collect_task SET leased_until = NULL, not_before = now() - interval '1 min'")
        pc = qtasks.lease_tasks(conn, "pc-worker", limit=99, modes=["fetch"])
        checks.append(("оренда modes=[fetch]: жодного render-джерела",
                       len(pc) > 0 and render_srcs.isdisjoint({t["source"] for t in pc}),
                       sorted({t["source"] for t in pc})))
        conn.execute("UPDATE collect_task SET leased_until = NULL, not_before = now() - interval '1 min'")
        ren = qtasks.lease_tasks(conn, "pc-worker2", limit=99, modes=["render"])
        checks.append(("оренда modes=[render]: лише render-джерела",
                       bool(ren) and all(t["source"] in render_srcs for t in ren),
                       sorted({t["source"] for t in ren})))
        conn.execute("UPDATE collect_task SET leased_until = NULL, not_before = now() - interval '1 min'")
        allm = qtasks.lease_tasks(conn, "pc-worker3", limit=99)          # None = телефон, усе
        checks.append(("оренда без modes (телефон) віддає й render-джерела",
                       {t["source"] for t in allm} >= render_srcs,
                       sorted({t["source"] for t in allm})))

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
