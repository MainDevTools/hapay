"""Черга-оренда розподіленого збору (T16, крок 1 — серверне ядро).

Модель: телефони-колектори ЗАБИРАЮТЬ роботу (pull), сервер лише тримає чергу і
розганяє конкурентів по часу. Балансування виходить само: більше телефонів онлайн →
черга тече швидше, але темп на КОЖНУ крамницю однаково обмежений.

Регулятори (рішення оператора 2026-07-19):
- SOURCE_SPACING_MIN=15 — мінімум між запитами до однієї крамниці (оренда зсуває
  not_before усіх задач source; різні крамниці — паралельно);
- repeat_min per-task (1440 = 1×/добу; хвіст 2880) — свіжість сторінки;
- LEASE_TTL_MIN=10 — телефон помер/заснув → оренда протухає, задача повертається.
"""
from __future__ import annotations

from psycopg.rows import dict_row

from api.ingest import CARD_SOURCES, COLLECT_MODE, HTML_SOURCES, source_listings

SOURCE_SPACING_MIN = 15   # розліт запитів по одній крамниці (хв)
LEASE_TTL_MIN = 10        # протухання оренди (хв)
HUB_REPEAT_MIN = 1440     # хаб (перелік акцій) — раз на добу, як і решта

# ── Періодичність за ГЛИБИНОЮ сторінки ────────────────────────────────────────────
# РІШЕННЯ ВЛАСНИКА 2026-07-21: для старту достатньо ОДНОГО збору на добу; підняття
# частоти відкладено до альфа-тесту. Це не компроміс якості, а точна відповідність
# задачі: 30-денний мінімум (Omnibus) рахується ПО ДОБАХ, тож другий замір за ту саму
# добу історії не додає — лише витрачає єдину пропускну здатність. Вивільнене йде у
# ширину: 449 запусків/добу → 251 при здатності ~384, тобто запас ~130 на нові категорії.
#
# Глибина: перші сторінки — де з'являються знижки; хвіст майже не рухається, тож йому
# вистачає разу на дві доби.
#
# ОБЕРЕЖНО З МЕТРИКОЮ (коштувало хибного висновку): `count(*) WHERE last_done_at >
# now() - '24 hours'` рахує ЗАДАЧІ, а не ЗАПУСКИ — його стеля дорівнює розміру черги.
# Погодинні бакети last_done_at теж дають лише НИЖНЮ межу: задача, зібрана двічі за
# годину, потрапляє в один бакет. Здатність ~384/добу виміряна саме бакетами.
PAGE_REPEAT_MIN = 1440     # перші сторінки — раз на добу (одна доба = одна точка історії)
DEEP_REPEAT_MIN = 2880     # глибші — раз на 2 доби (хвіст майже не рухається)
# Поріг «хвоста». Було 4; знижено до 2 (2026-07-23), коли 23 джерела замовили 1605
# запусків/добу при стелі 1226 (test_queue_load_fits_collector_capacity). Перші сторінки
# (785 лістингів — топ-товари й топ-акції всіх категорій) лишаються щоденними; сторінки
# 2+ дають точку раз на 2 доби — для 30-денного мінімуму Omnibus щільності досить
# (мінімум за вікно видно й з 15 точок), а бюджет черги вертається в межі (1206/1226).
DEEP_PAGE_FROM = 2
SITEMAP_REPEAT_MIN = 2880  # sitemap-відкриття — раз на 2 доби (нові товари з'являються рідко)
# Пріоритет sitemap ВИЩИЙ за картки (10 < 50): оренда в межах крамниці бере ORDER BY
# priority, і з дефолтними 100 sitemap голодував за будь-якої дозрілої картки — а після
# відкриття 186 карток (черга ~97% завантажена) голодував би майже вічно (впіймано на
# проді 2026-07-22: задача дозріла, збір іде, а її ніхто не бере). Один запит на 2 доби,
# що відсуває одну картку на 15 хв — ворота до всього іншого мають проходити першими.
SITEMAP_PRIORITY = 10
# Картки специфікацій (S12) — ЛИШЕ у вільні слоти: пріоритет нижчий (більший) за
# лістинги (100), тож у межах крамниці й у фінальному ORDER BY дозріла page-задача
# завжди обганяє card. Задача ОДНОРАЗОВА: при ok видаляється (специфікації не
# протухають), при збої лишається з бекофом.
CARD_PRIORITY = 200
CARD_PENDING_TARGET = 100   # дозування бекфілу: стільки card-задач тримаємо в черзі


# Стеля задач за одну оренду (застосунок просить 3; це лише ceiling проти зловживань).
# 20 → 40 (2026-07-23): джерел стало 28, і «по 1 задачі на крамницю за прохід» перестало
# влазити в стелю — повторний lease одразу віддавав хвіст замість порожнього.
MAX_LEASE = 40


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
    wanted: list[tuple[str, str]] = []
    for source, cfg in HTML_SOURCES.items():
        rows = []
        # хаб і sitemap — «ворота» до всього іншого, конкретної категорії не мають (slug=None)
        if cfg.get("hub"):
            rows.append((source, cfg["hub"], "hub", HUB_REPEAT_MIN, 100, None))
        if cfg.get("sitemap"):                          # sitemap-відкриття (T20): крамниця сама
            rows.append((source, cfg["sitemap"]["url"], "sitemap",
                         SITEMAP_REPEAT_MIN, SITEMAP_PRIORITY, None))
        for u, cat, page in source_listings(cfg):       # лістинги + їхня пагінація
            # slug категорії з конфігу лістинга — досі відкидався; на ньому тримається
            # оцінка цінності сторінки (0172), бо задача не має прямого звʼязку з товарами
            rows.append((source, u, "page", repeat_for_page(page), 100, cat))
        wanted += [(s, u) for s, u, _k, _r, _p, _c in rows]
        for source_, url, kind, rep, prio, slug in rows:
            got = conn.execute(
                "INSERT INTO collect_task (source, url, kind, repeat_min, priority, slug) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (source, url) DO UPDATE "
                "SET repeat_min = EXCLUDED.repeat_min, priority = EXCLUDED.priority, "
                "    slug = EXCLUDED.slug "
                "RETURNING (xmax = 0) AS inserted",
                (source_, url, kind, rep, prio, slug)).fetchone()
            n += 1 if got and got[0] else 0

    # ── прибрати задачі, які ВИБУЛИ з конфігу ────────────────────────────────────
    # Сів доти лише додавав, тож усе, що ми колись налаштували, лишалось у черзі
    # назавжди. Заміряно 2026-07-21: 12 задач Eldorado виду `.../page=2/` жили від
    # старого конфігу з пагінацією. Вони віддавали ПЕРШУ сторінку й чесно ставили
    # `ok` — тобто ми двічі на добу качали ту саму сторінку дванадцять разів, і
    # черга виглядала здоровою.
    #
    # Чистимо ЛИШЕ посіяні звідси: priority=100 (хаби/лістинги) та 10 (sitemap).
    # Лендинги/картки, знайдені discovery, мають priority=50 (enqueue_pages) — їх у
    # конфізі й не має бути за визначенням, і видалити їх означало б зламати двофазність.
    conn.execute(
        """DELETE FROM collect_task t
           WHERE t.priority IN (10, 100)
             AND NOT EXISTS (
                 SELECT 1 FROM unnest(%s::text[], %s::text[]) AS w(source, url)
                 WHERE w.source = t.source AND w.url = t.url)""",
        ([s for s, _ in wanted], [u for _, u in wanted]))
    return n


def seed_card_tasks(conn, target: int = CARD_PENDING_TARGET) -> int:
    """Дозований бекфіл специфікацій (S12): тримає в черзі ≤target одноразових
    card-задач — по ОДНІЙ картці на крос-групу (2+ джерел, скоуп оператора) без
    специфікації. Крамниця в групі — перша з CARD_SOURCES (порядок = пріоритет).

    Дозування навмисне: разовий сів усіх 4467 груп роздув би чергу й overdue-метрику
    сторожа (вона рахує «дозріла давно й не зібрана» — тисячі карток у вільних слотах
    саме такі). Викликається з lease; дешевий guard спершу — важкий запит по
    store_product не виконується, поки черга карток не просяде."""
    pending, = conn.execute(
        "SELECT count(*) FROM collect_task WHERE kind = 'card'").fetchone()
    need = target - pending
    if need <= 0:
        return 0
    rows = conn.execute(
        """WITH grp AS (
               SELECT match_key FROM store_product WHERE match_key IS NOT NULL
               GROUP BY match_key HAVING count(DISTINCT source_id) >= 2),
           has_spec AS (
               SELECT DISTINCT sp.match_key FROM product_spec
               JOIN store_product sp USING (store_product_id)
               WHERE sp.match_key IS NOT NULL),
           cand AS (
               SELECT DISTINCT ON (sp.match_key) s.name AS source, sp.url
               FROM store_product sp
               JOIN source s USING (source_id)
               JOIN grp USING (match_key)
               LEFT JOIN has_spec hs ON hs.match_key = sp.match_key
               WHERE s.name = ANY(%s) AND hs.match_key IS NULL
                 AND NOT EXISTS (SELECT 1 FROM collect_task t
                                 WHERE t.kind = 'card'
                                   AND t.source = s.name AND t.url = sp.url)
               ORDER BY sp.match_key, array_position(%s::text[], s.name),
                        sp.store_product_id)
           SELECT source, url FROM cand LIMIT %s""",
        (list(CARD_SOURCES), list(CARD_SOURCES), need)).fetchall()
    n = 0
    for source, url in rows:
        got = conn.execute(
            "INSERT INTO collect_task (source, url, kind, priority, repeat_min) "
            "VALUES (%s,%s,'card',%s,%s) ON CONFLICT (source, url) DO NOTHING "
            "RETURNING task_id",
            (source, url, CARD_PRIORITY, PAGE_REPEAT_MIN)).fetchone()
        n += 1 if got else 0
    return n


# Як часто перераховувати цінність сторінок. Запит агрегує весь store_product, тож
# на кожну оренду його ганяти не можна; цінність міняється повільно (нові групи,
# нові стеження) — кількох годин цілком досить.
VALUE_REFRESH_MIN = 360
VALUE_KEY = "task_value_refreshed_at"
# Скільки днів задача може простояти незібраною, перш ніж підніметься нагору попри
# низьку цінність. Без цього хвіст голодував би вічно (ту саму пастку вже ловили на
# sitemap 2026-07-22), а крамниця з одними лише «дешевими» сторінками випала б зовсім.
VALUE_ESCAPE_DAYS = 10


def refresh_task_value(conn, force: bool = False) -> int:
    """Перерахувати `value_tier` сторінок за виміряною цінністю їхньої категорії.

    Цінність = те, заради чого продукт існує: товари в КРОС-КРАМНИЧНИХ групах (дають
    «Де купити», «Наш вибір», порівняння), товари з активними знижками (їх і перевіряє
    Omnibus) і те, за чим СТЕЖАТЬ люди. Сторінка, чиї товари не дають нічого з цього,
    йде в хвіст: при обороті черги ≈26 днів вона все одно не набере придатної для
    30-денного вікна історії, а слот у когось відбирає.

    Звʼязок «задача → товари» непрямий: задача — це URL лістинга, тож рахуємо по
    категорії з конфігу (`slug`). Наближення свідоме — товар міг переїхати в іншу
    категорію на `refine_category`, — але воно на порядок краще за рівномірність.

    Повертає к-сть оновлених задач (0, якщо перерахунок ще не на часі)."""
    if not force:
        row = conn.execute(
            "SELECT valid_from FROM app_config WHERE key = %s "
            "ORDER BY valid_from DESC LIMIT 1", (VALUE_KEY,)).fetchone()
        if row and row[0] and (conn.execute(
                "SELECT now() - %s < make_interval(mins => %s)",
                (row[0], VALUE_REFRESH_MIN)).fetchone()[0]):
            return 0

    n = conn.execute(
        """WITH cat AS (
               SELECT s.name AS source, c.slug,
                      count(*) FILTER (WHERE sp.match_key IS NOT NULL) AS matched,
                      count(*) FILTER (WHERE d.store_product_id IS NOT NULL) AS discounted,
                      count(*) FILTER (WHERE w.watchlist_id IS NOT NULL) AS watched
               FROM store_product sp
               JOIN source s USING (source_id)
               JOIN category c USING (category_id)
               LEFT JOIN LATERAL (
                   SELECT de.store_product_id FROM discount_event de
                   WHERE de.store_product_id = sp.store_product_id
                     AND de.ended_at IS NULL LIMIT 1) d ON TRUE
               LEFT JOIN LATERAL (
                   SELECT wl.watchlist_id FROM watchlist wl
                   WHERE (wl.kind = 'store_product' AND wl.ref_id = sp.store_product_id)
                      OR (wl.kind = 'category' AND wl.query_text = c.slug) LIMIT 1) w ON TRUE
               GROUP BY 1, 2),
           scored AS (
               -- стеження важить найбільше: це пряма заявка людини, що товар їй потрібен
               SELECT source, slug, matched + 2 * discounted + 20 * watched AS score
               FROM cat),
           tiered AS (
               SELECT source, slug,
                      CASE WHEN score = 0 THEN 2
                           WHEN percent_rank() OVER (ORDER BY score) >= 0.70 THEN 0
                           ELSE 1 END AS tier
               FROM scored)
           UPDATE collect_task t SET value_tier = x.tier
           FROM tiered x
           WHERE t.slug = x.slug AND t.source = x.source AND t.value_tier <> x.tier""",
    ).rowcount

    # Картки специфікацій (S12) звʼязані з товаром напряму (url) — там цінність точна:
    # картка потрібна тій групі, що реально стоїть у кількох крамницях.
    n += conn.execute(
        """UPDATE collect_task t SET value_tier = CASE
               WHEN sp.match_key IS NOT NULL THEN 0 ELSE 1 END
           FROM store_product sp
           WHERE t.kind = 'card' AND sp.url = t.url
             AND t.value_tier <> CASE WHEN sp.match_key IS NOT NULL THEN 0 ELSE 1 END"""
    ).rowcount

    conn.execute("DELETE FROM app_config WHERE key = %s", (VALUE_KEY,))
    conn.execute("INSERT INTO app_config (key, value, valid_from) VALUES (%s,%s, now())",
                 (VALUE_KEY, "1"))
    return n


def lease_tasks(conn, worker: str, limit: int = 3,
                sources: list[str] | None = None) -> list[dict]:
    """Атомарно видати ≤limit дозрілих задач — ПО ОДНІЙ на крамницю (розліт).

    `sources` — колектор оголошує, що він УМІЄ. Різні колектори різні: телефон має
    WebView (render) і резидентний IP; сервер не має ні того, ні того, зате завжди
    ввімкнений. Без цього фільтра серверний колектор брав би задачі, які гарантовано
    провалить, і псував би їм лічильник збоїв замість того, щоб лишити телефону.

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
                       SELECT DISTINCT ON (source) task_id, priority, vkey, not_before
                       FROM (
                           SELECT task_id, source, priority, not_before,
                                  -- цінність (0172), АЛЕ із запобіжником: задача, яку не
                                  -- збирали VALUE_ESCAPE_DAYS, піднімається нагору попри
                                  -- тир. Без нього дешеві сторінки голодували б вічно —
                                  -- сувора пріоритетна черга при ємності < попиту хвіст
                                  -- не обслуговує ніколи (та сама пастка, що зі sitemap).
                                  CASE WHEN coalesce(last_done_at, created_at)
                                            < now() - make_interval(days => %s)
                                       THEN 0 ELSE value_tier END AS vkey
                           FROM collect_task
                           WHERE not_before <= now()
                             AND (leased_until IS NULL OR leased_until < now())
                             -- приведення потрібне В ОБОХ місцях: без нього
                             -- Postgres не виводить тип другого параметра
                             AND (%s::text[] IS NULL OR source = ANY(%s::text[]))
                       ) ready
                       ORDER BY source, priority, vkey, not_before   -- 1 задача/крамницю
                   ) pick
                   ORDER BY priority, vkey, not_before          -- цінніші й найдовше очікувані першими
                   LIMIT %s                                     -- → чесна ротація при джерелах > стелі
               )
                 AND not_before <= now()
                 AND (leased_until IS NULL OR leased_until < now())
               RETURNING task_id, source, url, kind""",
            (worker, LEASE_TTL_MIN, sources, sources, VALUE_ESCAPE_DAYS, limit)).fetchall()
    if leased:
        conn.execute(
            "UPDATE collect_task "
            "SET not_before = greatest(not_before, now() + make_interval(mins => %s)) "
            "WHERE source = ANY(%s)",
            (SOURCE_SPACING_MIN, [t["source"] for t in leased]))
        for t in leased:                    # режим збору per-source: fetch (GET) | render (WebView)
            t["mode"] = COLLECT_MODE.get(t["source"], "fetch")
            # sitemap — ЗАВЖДИ plain GET, навіть у render-крамниць: це статичний XML для
            # краулерів (без анти-боту), а WebView загорнув би його у власний XML-viewer
            # і віддав спотворений DOM замість сирого файлу.
            if t["kind"] == "sitemap":
                t["mode"] = "fetch"
    return leased


def complete_task(conn, task_id: int, worker: str, ok: bool, note: str | None = None) -> bool:
    """Закрити задачу після ingest. Успіх → наступний прохід через repeat_min;
    збій → експоненційний бекоф (крамниця, що дає 403/капчу, не довбається).
    kind='card' (S12) — одноразова: успіх видаляє задачу назавжди."""
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
           RETURNING task_id, kind""",
        ("ok" if ok else f"fail:{(note or '?')[:200]}", ok, ok, task_id, worker)).fetchone()
    if row and ok and row[1] == "card":
        conn.execute("DELETE FROM collect_task WHERE task_id = %s", (row[0],))
    return row is not None


def complete_by_url(conn, source: str, url: str, ok: bool = True,
                    note: str | None = None) -> bool:
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
    # ok=False (2026-07-23, «тихий нуль»): той самий бекоф, що в complete_task —
    # нульова сторінка не має вдавати здорову й довбати крамницю щодня без сенсу.
    row = conn.execute(
        """UPDATE collect_task
           SET last_done_at = now(),
               last_status = %s,
               fail_count = CASE WHEN %s THEN 0 ELSE fail_count + 1 END,
               leased_by = NULL, leased_until = NULL,
               not_before = now() + CASE WHEN %s
                   THEN make_interval(mins => repeat_min)
                   ELSE make_interval(mins => repeat_min * least(fail_count + 1, 8))
               END
           WHERE source = %s AND url = %s
             AND (leased_until IS NULL OR leased_until < now())
           RETURNING task_id, kind""",
        ("ok" if ok else f"fail:{(note or '?')[:200]}", ok, ok, source, url)).fetchone()
    if row and ok and row[1] == "card":      # card (S12) — одноразова, див. complete_task
        conn.execute("DELETE FROM collect_task WHERE task_id = %s", (row[0],))
    return row is not None


def enqueue_pages(conn, source: str, urls: list[str], *, priority: int = 50,
                  repeat_min: int = PAGE_REPEAT_MIN) -> int:
    """Дочірні сторінки з hub/sitemap-discovery → у чергу (замість миттєвого бурсту з
    телефона). not_before = +розліт (не бити крамницю одразу після хаба).

    `repeat_min` — політика повторного відкриття: sitemap-нащадки йдуть рідше (2880),
    бо їх БАГАТО (add.ua: 186 карток при здатності ~96/добу/крамницю — щоденний повтор
    фізично не влазить і роздував би overdue-метрику сторожа). ON CONFLICT оновлює
    repeat_min і в НАЯВНИХ задач: політика — не поточний стан (та сама філософія, що
    в seed_tasks); розклад (not_before/last_done_at) не чіпаємо."""
    n = 0
    for url in urls:
        got = conn.execute(
            "INSERT INTO collect_task (source, url, kind, priority, repeat_min, not_before) "
            "VALUES (%s,%s,'page',%s,%s, now() + make_interval(mins => %s)) "
            "ON CONFLICT (source, url) DO UPDATE SET repeat_min = EXCLUDED.repeat_min "
            "RETURNING (xmax = 0) AS inserted",
            (source, url, priority, repeat_min, SOURCE_SPACING_MIN)).fetchone()
        n += 1 if got and got[0] else 0
    return n


# Скільки хвилин тиші вважати відмовою.
#
# РІШЕННЯ ВЛАСНИКА 2026-07-21: 45 хв (було 90).
#
# Стара цифра трималась на хибному коментарі — «збір іде проходами приблизно раз на
# годину». Заміряно того ж дня по журналу оренд: телефон озивається кожні ~17.5 хв
# (14:12:34 · 14:29:43 · 14:47:10 — рівно, без розкиду). Отже 90 хв це не «пропущено
# щонайменше один прохід», а п'ять пропущених поспіль. Поріг був похідною від
# неправильної моделі, а не самостійним рішенням.
#
# Перевірка боєм того ж дня: колектор став о 14:49, о 16:18 сторож усе ще звітував
# «стан=ok · Збір працює · останній 89 хв тому». Півтори години простою, а звіт каже
# «працює» — саме те, за що ми критикуємо крамниці, тільки про власні дані.
#
# 45 хв ≈ два-три пропущені проходи: ще не паніка від однієї загубленої оренди
# (Android відкладає WorkManager), але вже сигнал, а не мовчання.
COLLECT_SILENT_MIN = 45


def collect_health(conn) -> dict:
    """Чи живий збір. Народилось із реальної відмови 2026-07-21: колектор стояв дві
    години (я сам зніс застосунок разом із токеном), і помітив це лише тому, що
    випадково дивився в базу. Оператор такої видимості не мав узагалі, а застосунок
    тим часом показував учорашні ціни як поточні — тобто рівно те, за що ми критикуємо
    крамниці.

    ⚠ МІРЯЄМО УСПІШНИЙ ЗБІР, А НЕ АКТИВНІСТЬ. Спершу тут стояло `max(last_done_at)`
    без огляду на статус — а невдала спроба теж проставляє `last_done_at`. Наслідок
    побачили 2026-07-21 о 16:20: телефон прокинувся, взяв по задачі на кожну з восьми
    крамниць, УСІ вісім упали з «Connection failure» — і показник бадьоро звітував
    «Збір працює · останній 2 хв тому». Свіжих цін не з'явилось жодної.
    Це найгірший різновид показника: він світиться зеленим саме тоді, коли все зламано.

    Тому свіжість рахуємо від останнього збору зі `last_status='ok'`, а спроби
    лишаємо окремо (`last_try_at`) — вони розрізняють два різні стани, яким
    потрібні різні дії:
        колектор мовчить            → телефон спить/помер, буди пристрій;
        колектор пробує, все падає  → мережа є до нас, але не до крамниць.

    ОБЕРЕЖНО з `tasks_done_*`: це к-сть ЗАДАЧ, яких торкались у вікні, а не к-сть
    ЗАПУСКІВ. Стеля дорівнює розміру черги, бо в рядку зберігається лише останній
    збір. Я вже раз сплутав це і зробив хибний висновок про пропускну здатність.
    """
    ok_only = "last_status = 'ok'"
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            f"""SELECT max(last_done_at) FILTER (WHERE {ok_only}) AS last_done_at,
                       max(last_done_at)                          AS last_try_at,
                       round(EXTRACT(epoch FROM
                             now() - max(last_done_at) FILTER (WHERE {ok_only})) / 60)::int
                           AS silent_min,
                       count(*) FILTER (WHERE {ok_only}
                                         AND last_done_at > now() - interval '1 hour')
                           AS tasks_done_1h,
                       count(*) FILTER (WHERE {ok_only}
                                         AND last_done_at > now() - interval '24 hours')
                           AS tasks_done_24h,
                       -- starts_with, а не LIKE із шаблоном: так у тексті запиту немає
                       -- жодного знака відсотка. psycopg сканує на плейсхолдери ВЕСЬ
                       -- запит, і «блукаючий» відсоток уже валив нам CI — див.
                       -- tests/test_sqlsafe.py (цей коментар ловився ним же).
                       count(*) FILTER (WHERE starts_with(last_status, 'fail')
                                         AND last_done_at > now() - interval '1 hour')
                           AS fails_1h,
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
    elif row["ok"]:
        row["note"] = f"Збір працює · останній {silent} хв тому"
    elif row["fails_1h"]:
        # найпідступніший стан: пристрій живий і бере роботу, але жодної свіжої ціни
        row["note"] = (f"Колектор працює, але запити падають — {row['fails_1h']} збоїв "
                       f"за годину, свіжого збору {silent} хв")
    else:
        row["note"] = f"Збір мовчить {silent} хв — перевір колектор"
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
