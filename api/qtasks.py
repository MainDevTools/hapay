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

from api.ingest import COLLECT_MODE, HTML_SOURCES, source_listings

SOURCE_SPACING_MIN = 15   # розліт запитів по одній крамниці (хв)
LEASE_TTL_MIN = 10        # протухання оренди (хв)
HUB_REPEAT_MIN = 720      # хаб (перелік акцій) — 2×/добу

# ── Періодичність за ГЛИБИНОЮ сторінки ────────────────────────────────────────────
# Заміряно на проді 2026-07-21 (за погодинними бакетами last_done_at): колектор дає
# ~20 задач/год ≈ 480 запусків на добу. Рівний розклад 720 хв на всі 248 задач вимагав
# 496 — тобто ми працювали ВПРИТУЛ до стелі, і 43 задачі були прострочені понад 12 год.
#
# ОБЕРЕЖНО з метрикою: `count(*) WHERE last_done_at > now() - '24 hours'` рахує ЗАДАЧІ,
# а не ЗАПУСКИ — його стеля дорівнює розміру черги. Я спершу взяв саме його (218) і
# зробив хибний висновок «розклад виконується на 44%». Реально було ~97%. Висновок
# «треба розводити періодичність» від цього не змінився, а ось число було брехливе.
# Погодинні бакети теж дають НИЖНЮ межу: задача, зібрана двічі, потрапляє в один бакет.
#
# Замість тиснути на крамниці частішими запитами розводимо періодичність: знижки
# з'являються на ПЕРШИХ сторінках лістинга, а глибокий хвіст майже не рухається —
# збирати його так само часто марно. Так найцінніші сторінки почнуть оновлюватись
# ЧАСТІШЕ, ніж зараз, при тій самій пропускній здатності.
PAGE_REPEAT_MIN = 720      # сторінки 1..3 — 2×/добу (тут живуть знижки)
DEEP_REPEAT_MIN = 2160     # сторінки 4+ — раз на 36 год (стабільний хвіст)
DEEP_PAGE_FROM = 4         # з якої сторінки вважаємо «хвостом»


MAX_LEASE = 20            # стеля задач за одну оренду (застосунок просить 3; це лише ceiling)


def repeat_for_page(page: int) -> int:
    """Період перезбору за номером сторінки лістинга (1 — перша)."""
    return PAGE_REPEAT_MIN if page < DEEP_PAGE_FROM else DEEP_REPEAT_MIN


def seed_tasks(conn) -> int:
    """Ідемпотентний сів черги з HTML_SOURCES (сервер — авторитет над списком).
    Нова крамниця/категорія в HTML_SOURCES → зʼявиться в черзі сама.

    Повертає к-сть НОВИХ задач. Розклад наявних (`not_before`, `last_done_at`) не
    чіпаємо — але `repeat_min` оновлюємо: це ПОЛІТИКА, а не поточний стан. Інакше
    зміна періодичності діяла б лише на задачі, створені після неї, і черга роками
    жила б за двома різними розкладами. `xmax = 0` відрізняє вставку від оновлення.
    """
    n = 0
    for source, cfg in HTML_SOURCES.items():
        rows = []
        if cfg.get("hub"):
            rows.append((source, cfg["hub"], "hub", HUB_REPEAT_MIN))
        for u, _cat, page in source_listings(cfg):      # лістинги + їхня пагінація
            rows.append((source, u, "page", repeat_for_page(page)))
        for source_, url, kind, rep in rows:
            got = conn.execute(
                "INSERT INTO collect_task (source, url, kind, repeat_min) "
                "VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (source, url) DO UPDATE SET repeat_min = EXCLUDED.repeat_min "
                "RETURNING (xmax = 0) AS inserted",
                (source_, url, kind, rep)).fetchone()
            n += 1 if got and got[0] else 0
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
        for t in leased:                    # режим збору per-source: fetch (GET) | render (WebView)
            t["mode"] = COLLECT_MODE.get(t["source"], "fetch")
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


def complete_by_url(conn, source: str, url: str) -> bool:
    """Закрити задачу за (source, url) — коли колектор зібрав сторінку БЕЗ task_id.

    Навіщо: у застосунку два шляхи збору. Черговий (`RunQueuePassAsync`) шле task_id,
    а ручний «зібрати все» (`RunAsync`) ходить за планом і task_id не має. Через це
    зібрані ним сторінки лишались у черзі «ще не брали»: черга перезбирала їх удруге,
    а `last_done_at` брехав. Заміряно 2026-07-21: ручний прохід приніс 623 товари Allo,
    і при цьому всі 30 задач Allo рахувались незібраними.

    Робимо це на СЕРВЕРІ, а не в застосунку, свідомо: оновлення застосунку йде через
    стори й доходить не до всіх, а сервер знає (source, url) → задача вже зараз.

    Оренду не вимагаємо (на відміну від complete_task): сторінку справді зібрано, і
    колектор автентифікований токеном. Але задачу, яку ЗАРАЗ орендує ХТОСЬ ІНШИЙ, не
    чіпаємо — інакше два колектори збивали б одне одному розклад.
    """
    row = conn.execute(
        """UPDATE collect_task
           SET last_done_at = now(), last_status = 'ok', fail_count = 0,
               leased_by = NULL, leased_until = NULL,
               not_before = now() + make_interval(mins => repeat_min)
           WHERE source = %s AND url = %s
             AND (leased_until IS NULL OR leased_until < now())
           RETURNING task_id""",
        (source, url)).fetchone()
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


# Скільки хвилин тиші вважати відмовою. Збір іде проходами приблизно раз на годину,
# тож 90 хв — це вже «пропущено щонайменше один», а не природна пауза.
COLLECT_SILENT_MIN = 90


def collect_health(conn) -> dict:
    """Чи живий збір. Народилось із реальної відмови 2026-07-21: колектор стояв дві
    години (я сам зніс застосунок разом із токеном), і помітив це лише тому, що
    випадково дивився в базу. Оператор такої видимості не мав узагалі, а застосунок
    тим часом показував учорашні ціни як поточні — тобто рівно те, за що ми критикуємо
    крамниці.

    ОБЕРЕЖНО з `tasks_done_*`: це к-сть ЗАДАЧ, яких торкались у вікні, а не к-сть
    ЗАПУСКІВ. Стеля дорівнює розміру черги, бо в рядку зберігається лише останній
    збір. Я вже раз сплутав це і зробив хибний висновок про пропускну здатність.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """SELECT max(last_done_at) AS last_done_at,
                      round(EXTRACT(epoch FROM now() - max(last_done_at)) / 60)::int
                          AS silent_min,
                      count(*) FILTER (WHERE last_done_at > now() - interval '1 hour')
                          AS tasks_done_1h,
                      count(*) FILTER (WHERE last_done_at > now() - interval '24 hours')
                          AS tasks_done_24h,
                      count(*) AS tasks_total,
                      count(*) FILTER (WHERE fail_count > 0) AS failing,
                      -- «дозріла давно й досі не зібрана» — ознака, що черга не встигає
                      count(*) FILTER (WHERE not_before < now() - interval '6 hours'
                                        AND (leased_until IS NULL OR leased_until < now()))
                          AS overdue
               FROM collect_task""").fetchone()
    silent = row["silent_min"]
    row["ok"] = silent is not None and silent <= COLLECT_SILENT_MIN
    row["silent_limit_min"] = COLLECT_SILENT_MIN
    if silent is None:
        row["note"] = "Збір ще не запускався"
    elif not row["ok"]:
        row["note"] = f"Збір мовчить {silent} хв — перевір колектор"
    else:
        row["note"] = f"Збір працює · останній {silent} хв тому"
    return row


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
