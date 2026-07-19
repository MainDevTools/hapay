"""Черга-оренда розподіленого збору (T16, крок 1 — серверне ядро).

Модель: телефони-колектори ЗАБИРАЮТЬ роботу (pull), сервер лише тримає чергу і
розганяє конкурентів по часу. Балансування виходить само: більше телефонів онлайн →
черга тече швидше, але темп на КОЖНУ крамницю однаково обмежений.

Регулятори (рішення оператора 2026-07-19):
- SOURCE_SPACING_MIN=15 — мінімум між запитами до однієї крамниці (оренда зсуває
  not_before усіх задач source; різні крамниці — паралельно);
- repeat_min per-task (дефолт 720 = 2×/добу) — свіжість сторінки;
- LEASE_TTL_MIN=10 — телефон помер/заснув → оренда протухає, задача повертається.
"""
from __future__ import annotations

from psycopg.rows import dict_row

from api.ingest import HTML_SOURCES

SOURCE_SPACING_MIN = 15   # розліт запитів по одній крамниці (хв)
LEASE_TTL_MIN = 10        # протухання оренди (хв)
HUB_REPEAT_MIN = 720      # хаб (перелік акцій) — 2×/добу
PAGE_REPEAT_MIN = 720     # лістинг/лендинг — 2×/добу
MAX_LEASE = 20            # стеля задач за одну оренду (застосунок просить 3; це лише ceiling)


def seed_tasks(conn) -> int:
    """Ідемпотентний сів черги з HTML_SOURCES (сервер — авторитет над списком).
    Нова крамниця/категорія в HTML_SOURCES → зʼявиться в черзі сама; наявним
    задачам розклад НЕ скидається (ON CONFLICT DO NOTHING)."""
    n = 0
    for source, cfg in HTML_SOURCES.items():
        rows = []
        if cfg.get("hub"):
            rows.append((source, cfg["hub"], "hub", HUB_REPEAT_MIN))
        for u in cfg.get("urls", ()):
            rows.append((source, u, "page", PAGE_REPEAT_MIN))
        for source_, url, kind, rep in rows:
            got = conn.execute(
                "INSERT INTO collect_task (source, url, kind, repeat_min) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (source, url) DO NOTHING RETURNING 1",
                (source_, url, kind, rep)).fetchone()
            n += 1 if got else 0
    return n


def lease_tasks(conn, worker: str, limit: int = 3) -> list[dict]:
    """Атомарно видати ≤limit дозрілих задач — ПО ОДНІЙ на крамницю (розліт).

    Конкурентна безпека: у READ COMMITTED другий UPDATE перечитує WHERE на вже
    оновленому рядку → умова «вільна» хибна → рядок мовчки випадає. Два телефони
    не отримають ту саму задачу. Потім not_before УСІХ задач орендованих source
    зсувається на +SOURCE_SPACING_MIN — «1 запит/крамниця/15 хв».
    """
    limit = max(1, min(int(limit), MAX_LEASE))
    with conn.cursor(row_factory=dict_row) as cur:
        leased = cur.execute(
            """UPDATE collect_task
               SET leased_by = %s,
                   leased_until = now() + make_interval(mins => %s)
               WHERE task_id IN (
                   SELECT task_id FROM (
                       SELECT DISTINCT ON (source) task_id, priority, not_before
                       FROM collect_task
                       WHERE not_before <= now()
                         AND (leased_until IS NULL OR leased_until < now())
                       ORDER BY source, priority, not_before   -- 1 задача/крамницю
                   ) pick
                   ORDER BY priority, not_before                -- НАЙДОВШЕ очікувані першими (не абетка)
                   LIMIT %s                                     -- → чесна ротація при джерелах > стелі
               )
                 AND not_before <= now()
                 AND (leased_until IS NULL OR leased_until < now())
               RETURNING task_id, source, url, kind""",
            (worker, LEASE_TTL_MIN, limit)).fetchall()
    if leased:
        conn.execute(
            "UPDATE collect_task "
            "SET not_before = greatest(not_before, now() + make_interval(mins => %s)) "
            "WHERE source = ANY(%s)",
            (SOURCE_SPACING_MIN, [t["source"] for t in leased]))
    return leased


def complete_task(conn, task_id: int, worker: str, ok: bool, note: str | None = None) -> bool:
    """Закрити задачу після ingest. Успіх → наступний прохід через repeat_min;
    збій → експоненційний бекоф (крамниця, що дає 403/капчу, не довбається)."""
    row = conn.execute(
        """UPDATE collect_task
           SET leased_by = NULL, leased_until = NULL,
               last_done_at = now(),
               last_status = %s,
               fail_count = CASE WHEN %s THEN 0 ELSE fail_count + 1 END,
               not_before = now() + CASE WHEN %s
                   THEN make_interval(mins => repeat_min)
                   ELSE make_interval(mins => repeat_min * least(fail_count + 1, 8))
               END
           WHERE task_id = %s AND leased_by = %s
           RETURNING task_id""",
        ("ok" if ok else f"fail:{(note or '?')[:200]}", ok, ok, task_id, worker)).fetchone()
    return row is not None


def enqueue_pages(conn, source: str, urls: list[str], *, priority: int = 50) -> int:
    """Дочірні сторінки з hub-discovery → у чергу (замість миттєвого бурсту з телефона).
    not_before = +розліт (не бити крамницю одразу після хаба); наявним розклад не чіпаємо."""
    n = 0
    for url in urls:
        got = conn.execute(
            "INSERT INTO collect_task (source, url, kind, priority, repeat_min, not_before) "
            "VALUES (%s,%s,'page',%s,%s, now() + make_interval(mins => %s)) "
            "ON CONFLICT (source, url) DO NOTHING RETURNING 1",
            (source, url, priority, PAGE_REPEAT_MIN, SOURCE_SPACING_MIN)).fetchone()
        n += 1 if got else 0
    return n


def queue_stats(conn) -> list[dict]:
    """Зріз черги для оператора: скільки задач/дозрілих/збійних по крамницях."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT source,
                      count(*) AS tasks,
                      count(*) FILTER (WHERE not_before <= now()
                                        AND (leased_until IS NULL OR leased_until < now())) AS ready,
                      count(*) FILTER (WHERE leased_until >= now()) AS leased,
                      count(*) FILTER (WHERE fail_count > 0) AS failing,
                      min(not_before) AS next_at
               FROM collect_task GROUP BY source ORDER BY source""").fetchall()
