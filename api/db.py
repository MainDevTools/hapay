"""Query-хелпери read-API (§9.1/§9.2). Лише читання (+watchlist). dict-рядки для JSON.

Клієнт сюди не має прямого доступу — тільки через api/main.py (§8.10.1).
Гроші повертаємо в копійках (int); формат у грн — на клієнті.
"""
from __future__ import annotations
import math

from psycopg import errors
from psycopg.rows import dict_row
from search import search_patterns
from taxonomy import category_ui, slugs_in_section, SECTION_ORDER

# сортування — без de.-префікса: колонки беруться з CTE `best` (див. list_discounts)
_SORTS = {
    "verified": "verified_pct DESC NULLS LAST, computed_at DESC",
    "discount": "declared_pct DESC NULLS LAST, computed_at DESC",
    "new":      "computed_at DESC",
}

# promo_until віддаємо лише коли дата РЕАЛЬНА: майбутня й у розумних межах (≤90 днів).
# Так відсіюється генерична далека дата (Rozetka ставить 2027 для не-знижкових) і «сьогодні».
_PROMO_COL = ("CASE WHEN sp0.promo_until > CURRENT_DATE "
              "AND sp0.promo_until <= CURRENT_DATE + 90 "
              "THEN to_char(sp0.promo_until, 'YYYY-MM-DD') END AS promo_until,")


def product_card(conn, store_product_id: int):
    """Один товар як КАРТКА — для сторінки /product/{id} на сайті (S19).

    `product_offers` навмисно бідний: він відповідає на питання «де ще це продають» і
    віддає лише крамницю+ціну+URL. Сторінці товару цього мало — потрібні фото, бейдж
    перевірки та 30-денна база, інакше вона показує порожнє місце там, де в продукту
    головне твердження. Тому окремий запит, а не роздування `offers`.

    Ціну беремо з АКТИВНОЇ події, якщо вона є; інакше — з останнього снапшота, бо
    товар без активної знижки теж має сторінку (на нього можна прийти зі стеження)."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT sp.store_product_id, sp.title, sp.url, sp.image_url, sp.variant_note,
                      pr.product_id, s.name AS store, c.slug AS category_slug, c.name AS category,
                      COALESCE(de.current_kop, ps.price_now_kop) AS current_kop,
                      COALESCE(de.old_declared_kop, ps.price_old_kop) AS old_declared_kop,
                      de.reference_kop, de.declared_pct, de.verified_pct, de.badge_state,
                      (SELECT count(DISTINCT g.source_id) FROM store_product g
                        WHERE sp.match_key IS NOT NULL AND g.match_key = sp.match_key)
                        AS group_stores
               FROM store_product sp
               JOIN source s USING (source_id)
               JOIN category c ON c.category_id = sp.category_id
               LEFT JOIN product pr ON pr.match_key = sp.match_key
               LEFT JOIN discount_event de
                      ON de.store_product_id = sp.store_product_id AND de.ended_at IS NULL
               LEFT JOIN LATERAL (
                   SELECT price_now_kop, price_old_kop FROM price_snapshot
                   WHERE store_product_id = sp.store_product_id
                   ORDER BY seen_at DESC LIMIT 1) ps ON TRUE
               WHERE sp.store_product_id = %s""", (store_product_id,)).fetchone()


def list_discounts(conn, category=None, badge=None, sort="verified", limit=50, offset=0, q=None,
                   price_min=None, price_max=None, section=None):
    """Стрічка знижок — АГРЕГАТОРНА (T15/§17): одна картка на ТОВАР, не на крамницю.

    Товари з однаковим ключем (match_key = GTIN, інакше артикул) колапсуються в одну
    картку, яку представляє НАЙДЕШЕВША пропозиція (клієнт показує «від X ₴· в N
    крамницях», а не назву однієї крамниці — інакше «чому Foxtrot, а не Allo?»). Товари
    без ключа — кожен сам собі (gkey='sp:<id>').
    `offers_n` = к-сть РІЗНИХ крамниць у групі; «Де купити» (product_offers) деталізує.
    """
    where = ["de.ended_at IS NULL"]
    params: list = []
    if category:
        where.append("c.slug = %s"); params.append(category)
    elif section:
        # Розділ = набір категорій (мапа живе в taxonomy, у БД розділу нема). Конкретна
        # категорія має пріоритет: вона вужча, тож поєднувати їх нема сенсу.
        where.append("c.slug = ANY(%s)"); params.append(slugs_in_section(section))
    if badge:
        # `verified` тягне за собою й provisional (див. BADGE_FILTERS); решта станів —
        # самі по собі. Раніше тут стояло `= %s` на сирому значенні, тож ?badge=verified
        # мовчки губив provisional-картки.
        where.append("de.badge_state = ANY(%s)")
        params.append(BADGE_FILTERS.get(badge, [badge]))
    if q:                                   # пошук за назвою (ILIKE — прощає часткові; §9.1)
        # ILIKE ANY: оригінал + кирилиця-бренд→латиниця («айфон»→iPhone); див. search.py
        where.append("sp.title ILIKE ANY(%s)"); params.append(search_patterns(q))
    if price_min is not None:               # ціна — копійки (інв. A); фільтр за поточною ціною
        where.append("de.current_kop >= %s"); params.append(price_min)
    if price_max is not None:
        where.append("de.current_kop <= %s"); params.append(price_max)
    order = _SORTS.get(sort, _SORTS["verified"])
    sql = f"""
        WITH ev AS (
            SELECT de.discount_event_id, sp.store_product_id, sp.title, sp.url, sp.image_url,
                   sp.variant_note, sp.match_key, s.name AS store,
                   de.current_kop, de.old_declared_kop, de.reference_kop,
                   de.declared_pct, de.verified_pct, de.badge_state, de.computed_at,
                   COALESCE(sp.match_key, 'sp:' || sp.store_product_id) AS gkey
            FROM discount_event de
            JOIN store_product sp USING (store_product_id)
            JOIN source s USING (source_id)
            JOIN category c ON c.category_id = sp.category_id
            WHERE {' AND '.join(where)}
        ),
        best AS (   -- одна картка на групу: представляє найдешевша (в наявності пріоритетно)
            SELECT DISTINCT ON (gkey)
                   discount_event_id, store_product_id, title, url, image_url, variant_note,
                   match_key, store, current_kop, old_declared_kop, reference_kop,
                   declared_pct, verified_pct, badge_state, computed_at
            FROM ev
            ORDER BY gkey, current_kop, badge_state
        )
        SELECT b.discount_event_id, b.store_product_id, b.title, b.url, b.image_url,
               b.variant_note, b.store, b.current_kop, b.old_declared_kop, b.reference_kop,
               b.declared_pct, b.verified_pct, b.badge_state,
               {_PROMO_COL}
               CASE WHEN b.match_key IS NULL THEN 1
                    ELSE (SELECT count(DISTINCT sp2.source_id)
                          FROM store_product sp2 WHERE sp2.match_key = b.match_key)
               END AS offers_n
        FROM best b
        JOIN store_product sp0 USING (store_product_id)
        ORDER BY {order}
        LIMIT %s OFFSET %s"""
    params += [limit, offset]
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def product_history(conn, store_product_id: int, days: int = 90):
    """Денні точки для графіка (§9.2) — із СИРОГО price_snapshot (in_stock), надійніше за cagg на свіжих даних.

    `n` — скільки вимірів за добу: provenance для §5.4 (показуємо основу, а не лише лінію).
    Доби без вимірів у вибірці ВІДСУТНІ — графік мусить це показати як розрив (T12).
    """
    sql = """
        SELECT (seen_at AT TIME ZONE 'Europe/Kyiv')::date AS day,
               min(price_now_kop) AS min_kop, max(price_now_kop) AS max_kop,
               count(*) AS n
        FROM price_snapshot
        WHERE store_product_id = %s AND in_stock
          AND seen_at > now() - make_interval(days => %s)
        GROUP BY day ORDER BY day"""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (store_product_id, days)).fetchall()


def product_specs(conn, store_product_id: int):
    """Характеристики групи товару (S12): спершу специфікація САМОГО товару, інакше
    найсвіжіша серед членів його крос-групи (той самий товар — специфікації спільні).
    Провенанс завжди в відповіді (інваріант B5): крамниця + URL картки + дата збору."""
    sql = """
        WITH me AS (SELECT store_product_id, match_key FROM store_product
                    WHERE store_product_id = %s)
        SELECT ps.spec_id, s.name AS store, ps.source_url,
               to_char(ps.collected_at AT TIME ZONE 'Europe/Kyiv', 'YYYY-MM-DD')
                   AS collected_day
        FROM product_spec ps
        JOIN store_product sp USING (store_product_id)
        JOIN source s USING (source_id)
        WHERE sp.store_product_id = (SELECT store_product_id FROM me)
           OR (sp.match_key IS NOT NULL
               AND sp.match_key = (SELECT match_key FROM me))
        ORDER BY (sp.store_product_id = (SELECT store_product_id FROM me)) DESC,
                 ps.collected_at DESC
        LIMIT 1"""
    with conn.cursor(row_factory=dict_row) as cur:
        head = cur.execute(sql, (store_product_id,)).fetchone()
        if head is None:
            return None
        attrs = cur.execute(
            "SELECT name, value FROM spec_attr WHERE spec_id = %s ORDER BY position",
            (head["spec_id"],)).fetchall()
    return {"store": head["store"], "source_url": head["source_url"],
            "collected_day": head["collected_day"], "attrs": attrs}


# сортування для «усіх товарів» (не лише знижок) — колонки з CTE best нижче
# кваліфікуємо b.* — бо JOIN store_product sp0 (для promo_until) теж має first_seen_at
# Фільтри стрічки за станом перевірки. Ключ — те, що просить клієнт; значення — стани
# discount_event, які під нього підпадають.
#   verified — пройшли перевірку 30-денним мінімумом; provisional теж пройшли, лише на
#              ще неповному вікні (чесний стан молодих даних, не другий сорт);
#   pumped   — «стара» ціна вища за фактичний 30-денний мінімум (ст. §5 / Omnibus).
#              Показуємо ФАКТ про ціну, не вирок крамниці — формулювання в UI те саме,
#              що на картці: «⚠ «стара» ціна завищена».
BADGE_STATES = ("declared", "verified", "verified_provisional",
                "pumped", "insufficient_history")
BADGE_FILTERS = {s: [s] for s in BADGE_STATES}
BADGE_FILTERS["verified"] = ["verified", "verified_provisional"]

_PSORTS = {
    "discount":  "b.declared_pct DESC NULLS LAST, b.first_seen_at DESC",   # спочатку знижки
    "new":       "b.first_seen_at DESC",
    "cheap":     "b.current_kop ASC",
    "expensive": "b.current_kop DESC",
    # «популярні моделі» (§17): товар, який продають НАЙБІЛЬШЕ крамниць — його найкраще
    # порівнювати (offers_n — вихідний алias, Postgres дозволяє ORDER BY по ньому)
    "popular":   "offers_n DESC NULLS LAST, b.declared_pct DESC NULLS LAST",
    # «де дешевше»: спершу картки, де той самий артикул дешевший в іншій крамниці,
    # від найбільшої різниці. Сигнал рідкісний (заміряно 2026-07-21: 1.8% карток,
    # на першій сторінці ноутбуків — жодного), тож без цього сортування людина його
    # просто не зустріне. ch.kop — з LATERAL нижче, у ORDER BY вже в області видимості.
    "cheaper":   "(ch.kop IS NOT NULL) DESC, (b.current_kop - ch.kop) DESC NULLS LAST, "
                 "b.declared_pct DESC NULLS LAST",
}

# Уцінка / відновлене — ІНШИЙ СТАН товару, не «те саме дешевше».
#
# ЄДИНЕ джерело цього правила: воно знадобилось уже в пʼятьох місцях — бейдж «дешевше
# в іншій крамниці», сигнал «знижка нічого не дає», фото плитки категорії, вибір
# представника групи і «Де купити». Доти жило у двох константах, які неминуче
# розійшлись би. Міняти стан речі → міняти ТУТ.
#
# Заміряно на живих даних 2026-07-21, чому це не дрібниця: груп, де поруч є уцінений
# і чистий товар — 10, і у 8 із них уцінений НАЙДЕШЕВШИЙ. Без поділу він щоразу
# ставав би «найкращою ціною».
_USED_RE = r'уцінк|уценк|відновлен|восстановлен|refurbish'

# ── «Знижка нічого не дає»: пороги (рішення власника 2026-07-21, інваріант C) ──────
#
# ЦЕ НЕ статутний `pumped` (§5). Той рахується з ІСТОРІЇ цін тієї самої крамниці
# (мінімум за 30 днів, Omnibus) і ми його не чіпаємо. Тут інше джерело доказу —
# ЦІНИ КОНКУРЕНТІВ ЗАРАЗ. Тому й кажемо лише факт («у N крамницях така сама ціна»),
# а не вирок: чужі ціни юридично не спростовують чиюсь стару ціну.
#
# Правило вивелось із живих даних, і два простіші варіанти довелось відкинути:
#   · «стара ціна вища за ринок» ловило загальні зниження РРЦ — три крамниці
#     узгоджено називали ту саму стару ціну, тобто це не накачування;
#   · «ціна така сама, як у ринку» спрацьовує на 89% знижкових карток (1464 з 1648) —
#     це норма ринку, а не сигнал.
_HOLLOW_MIN_PCT = 20      # знижка має бути ГУЧНОЮ — інакше суперечність не варта уваги
_HOLLOW_MIN_PEERS = 2     # одна крамниця — ще не ринок
_HOLLOW_SAME_PRICE = 1.02  # «та сама ціна» = у межах +2%: копійчані розбіжності не рахуємо


def list_products(conn, category=None, sort="discount", limit=50, offset=0, q=None,
                  section=None,
                  price_min=None, price_max=None, only_discounts=False, badge=None):
    """УСІ товари (не лише знижкові), остання відома ціна кожного, MPN-дедуп як стрічка.

    Розворот у бік повного прайс-агрегатора: показуємо весь зібраний каталог, а знижка —
    бейдж на картці (has_discount), не єдиний критерій. `only_discounts=True` звужує до
    знижкових (сумісність зі старою стрічкою). Ціна — з останнього price_snapshot.

    `cheaper_kop`/`cheaper_store` — та сама модель (той самий match_key) ДЕШЕВШЕ в іншій крамниці.
    Сенс: представника групи обирає `best` — «знижкова пріоритетно, тоді найдешевша»,
    тож картка з гучним −47% цілком може бути дорожчою за звичайну ціну поруч. Це і є
    суть «Хапая», тож кажемо про це прямо, навіть коли це псує вигляд власної знижки.

    ВАЖЛИВО, чому фільтри розділені на базові й звужувальні: кандидатів на «дешевше»
    беремо з `ev` ДО звуження. Якби мінімум рахувався після `only_discounts` (а це
    режим гортання за замовчуванням), він бачив би лише знижкові пропозиції — тобто
    саме те, з чим порівнюємо, — і бейдж не спрацював би НІ РАЗУ.
    """
    base = ["sp.last_seen_at > now() - interval '3 days'", "l.in_stock"]
    params: list = [_USED_RE]      # 1-й %s — у SELECT ev (прапорець `used`)
    if category:
        base.append("c.slug = %s"); params.append(category)
    elif section:                      # розділ = набір категорій (мапа в taxonomy)
        base.append("c.slug = ANY(%s)"); params.append(slugs_in_section(section))

    # звужувальні — лише для ВИБОРУ картки, не для пошуку дешевшої пропозиції
    narrow: list[str] = []
    if q:
        narrow.append("title ILIKE ANY(%s)"); params.append(search_patterns(q))
    if price_min is not None:
        narrow.append("current_kop >= %s"); params.append(price_min)
    if price_max is not None:
        narrow.append("current_kop <= %s"); params.append(price_max)
    if only_discounts:
        narrow.append("discount_event_id IS NOT NULL")
    if badge:
        # ⚠ Було `if badge == "verified"` — будь-яке інше значення МОВЧКИ ігнорувалось:
        # `?badge=pumped` віддавав повний каталог, ніби фільтр застосовано (2026-07-26).
        # Тепер невідоме значення відсікає ендпойнт (400), а тут лишається лише мапа.
        narrow.append("badge_state = ANY(%s)")
        params.append(BADGE_FILTERS[badge])
    narrow_sql = ("WHERE " + " AND ".join(narrow)) if narrow else ""

    order = _PSORTS.get(sort, _PSORTS["discount"])
    # Сторінка-СПЕРШУ (2026-07-24, скарга на затримки): збагачення «дешевше деінде» /
    # «порожня знижка» рахувалось для ВСІХ ~31k груп, тоді сортувалось і бралось 50 —
    # 0.83 с на глобальній стрічці. Тепер сторінку обираємо ДО збагачення (сорти
    # discount/new/cheap/expensive ранжують колонками best) і збагачуємо лише її.
    # Винятки: «cheaper» ранжує САМИМ збагаченням (ch.kop) → легасі-шлях повним
    # проходом; «popular» ранжуємо легким агрегатом по ev (к-сть свіжих крамниць
    # групи) замість підзапиту offers_n на кожен рядок — показуваний offers_n
    # лишається точним (рахується підзапитом уже для 50).
    page_first = sort != "cheaper"
    popular = sort == "popular"
    page_order = "pop.n DESC, b.declared_pct DESC NULLS LAST" if popular else order
    head = f"""
        WITH latest AS (   -- остання ціна кожного товару (index-scan по ix_ps_prod_window)
            SELECT DISTINCT ON (ps.store_product_id)
                   ps.store_product_id, ps.price_now_kop AS current_kop,
                   ps.price_old_kop AS old_declared_kop, ps.in_stock
            FROM price_snapshot ps
            ORDER BY ps.store_product_id, ps.seen_at DESC
        ),
        ev AS (
            SELECT l.store_product_id, sp.title, sp.url, sp.image_url, sp.variant_note, sp.match_key,
                   s.name AS store, sp.source_id, sp.first_seen_at,
                   l.current_kop, l.old_declared_kop,
                   de.discount_event_id, de.declared_pct, de.verified_pct,
                   COALESCE(de.badge_state, 'none') AS badge_state,
                   COALESCE(sp.match_key, 'sp:' || sp.store_product_id) AS gkey,
                   (sp.title ~* %s) AS used,
                   -- відсоток ІЗ СИРОГО снапшота (як його показує картка), а не з
                   -- discount_event: порівнювати треба саме те, що бачить людина
                   CASE WHEN l.old_declared_kop > l.current_kop
                        THEN round((l.old_declared_kop - l.current_kop) * 100.0
                                   / l.old_declared_kop)::int
                        ELSE 0 END AS shown_pct
            FROM latest l
            JOIN store_product sp USING (store_product_id)
            JOIN source s USING (source_id)
            JOIN category c ON c.category_id = sp.category_id
            LEFT JOIN discount_event de
                   ON de.store_product_id = l.store_product_id AND de.ended_at IS NULL
            WHERE {' AND '.join(base)}
        ),
        best AS (   -- одна картка на групу (MPN): найдешевша, знижкова пріоритетно
            SELECT DISTINCT ON (gkey)
                   gkey, store_product_id, title, url, image_url, variant_note, match_key, store,
                   source_id, first_seen_at, current_kop, old_declared_kop, declared_pct,
                   verified_pct, badge_state, discount_event_id, shown_pct
            FROM ev {narrow_sql}
            -- `used` ПЕРШИМ: уцінене/відновлене не може представляти групу, поки в ній
            -- є чиста пропозиція. Інакше картка бере в уціненого і назву, і фото, і ціну:
            -- на проді «УЦІНКА Телевізор LG 50UA75006LA — від 16 999 ₴» очолювала групу,
            -- де ВІСІМ крамниць продають новий (заміряно 2026-07-21: таких груп 10).
            -- Якщо чистих у групі нема — уцінене лишається представником, товар реальний.
            ORDER BY gkey, used, (discount_event_id IS NOT NULL) DESC, current_kop
        ),"""

    # «popular» ранжує к-стю свіжих крамниць групи (легкий агрегат) — точний offers_n
    # для показу однаково рахується нижче, вже лише для сторінки
    pop_cte = ("""
        pop AS (SELECT gkey, count(DISTINCT source_id) AS n FROM ev GROUP BY gkey),"""
               if popular else "")
    page_cte = (f"""
        page AS (   -- сторінку обираємо ДО збагачення: LIMIT тут, не в кінці
            SELECT b.* FROM best b {"JOIN pop USING (gkey)" if popular else ""}
            ORDER BY {page_order} LIMIT %s OFFSET %s
        ),""" if page_first else "")
    alt_scope = "AND gkey IN (SELECT gkey FROM page) " if page_first else ""
    src = "page" if page_first else "best"
    tail = "" if page_first else "LIMIT %s OFFSET %s"
    final_order = ("offers_n DESC NULLS LAST, b.declared_pct DESC NULLS LAST"
                   if popular else order)

    sql = head + pop_cte + page_cte + f"""
        alt AS (   -- кандидати «дешевше деінде»: уся група, БЕЗ уцінених/відновлених
            SELECT gkey,
                   array_agg(current_kop ORDER BY current_kop) AS kops,
                   array_agg(source_id   ORDER BY current_kop) AS srcs,
                   array_agg(store       ORDER BY current_kop) AS stores,
                   array_agg(shown_pct   ORDER BY current_kop) AS pcts
            FROM ev WHERE NOT used {alt_scope}GROUP BY gkey
        )
        SELECT b.store_product_id, b.title, b.url, b.image_url, b.variant_note, b.store,
               b.current_kop, b.old_declared_kop, b.declared_pct, b.verified_pct, b.badge_state,
               (b.discount_event_id IS NOT NULL) AS has_discount,
               ch.kop AS cheaper_kop, ch.store AS cheaper_store,
               -- «знижка нічого не дає»: скільки ІНШИХ крамниць тримають ту саму ціну,
               -- не заявляючи порівнянної знижки. NULL = правило не спрацювало.
               CASE WHEN b.shown_pct >= {_HOLLOW_MIN_PCT}
                     AND ch.kop IS NULL                       -- дешевших нема: інакше про це
                     AND hol.n >= {_HOLLOW_MIN_PEERS}         -- вже каже cheaper_store
                    THEN hol.n END AS same_price_n,
               {_PROMO_COL}
               CASE WHEN b.match_key IS NULL THEN 1
                    ELSE (SELECT count(DISTINCT sp2.source_id)
                          FROM store_product sp2 WHERE sp2.match_key = b.match_key)
               END AS offers_n
        FROM {src} b
        JOIN store_product sp0 USING (store_product_id)
        LEFT JOIN alt a USING (gkey)
        -- найдешевша пропозиція ІНШОЇ крамниці, дешевша за показану. «Іншої» —
        -- бо родовий артикул буває спільний для кольорів у тій самій крамниці
        -- (див. product_offers), і «дешевше в Rozetka» на картці Rozetka — дурня.
        LEFT JOIN LATERAL (
            SELECT t.kop, t.store
            FROM unnest(a.kops, a.srcs, a.stores) AS t(kop, src, store)
            WHERE t.src <> b.source_id AND t.kop < b.current_kop
            ORDER BY t.kop LIMIT 1
        ) ch ON TRUE
        -- Крамниці з ТІЄЮ САМОЮ ціною, які НЕ заявляють жодної знижки (pct = 0).
        -- Саме вони роблять гучну знижку порожньою: та сама ціна доступна без акції.
        -- (Знак відсотка тут писати НЕ МОЖНА навіть у коментарі: psycopg сканує на
        --  плейсхолдери весь текст запиту й ламає розбір ще до відправки. Стереже
        --  tests/test_sqlsafe.py — він і спіймав цей коментар, коли я написав приклад
        --  із самим знаком.)
        --
        -- Чому саме «= 0», а не «удвічі менша за нашу» (був і такий варіант): рівно
        -- нуль дозволяє сказати людині «така сама ціна БЕЗ ЗНИЖКИ» і не збрехати.
        -- Заодно це надійніше відсікає загальні зниження РРЦ: крамниця, яка нічого
        -- не оголошує, точно не учасник спільної акції.
        LEFT JOIN LATERAL (
            SELECT count(*)::int AS n
            FROM unnest(a.kops, a.srcs, a.pcts) AS t(kop, src, pct)
            WHERE t.src <> b.source_id
              AND t.kop >= b.current_kop
              AND t.kop <= b.current_kop * {_HOLLOW_SAME_PRICE}
              AND t.pct = 0
        ) hol ON TRUE
        ORDER BY {final_order}
        {tail}"""
    params += [limit, offset]   # позиційно збігається в обох формах: page-CTE або хвіст
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def compare_products(conn, ids: list[int]) -> dict:
    """Порівняння 2-4 товарів side-by-side (S14). Для кожного id — базові факти
    (назва/фото/ціна/бейдж/offers_n) + об'єднана таблиця характеристик (union атрибутів
    з product_specs S12, вирівняна по колонках; відсутнє = None). Порядок колонок =
    порядок ids. Жодних оцінок — лише факти з провенансом (інваріант B)."""
    ids = [int(i) for i in ids][:4]                 # UI-стеля колонок
    if len(ids) < 2:
        return {"products": [], "spec_rows": []}
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (ps.store_product_id) ps.store_product_id, ps.price_now_kop
            FROM price_snapshot ps WHERE ps.store_product_id = ANY(%s)
            ORDER BY ps.store_product_id, ps.seen_at DESC
        )
        SELECT sp.store_product_id, sp.title, sp.image_url, l.price_now_kop AS price_kop,
               COALESCE(de.badge_state, 'none') AS badge_state, de.declared_pct,
               CASE WHEN sp.match_key IS NULL THEN 1
                    ELSE (SELECT count(DISTINCT sp2.source_id) FROM store_product sp2
                          WHERE sp2.match_key = sp.match_key)
               END AS offers_n
        FROM store_product sp
        LEFT JOIN latest l USING (store_product_id)
        LEFT JOIN discount_event de ON de.store_product_id = sp.store_product_id
                                   AND de.ended_at IS NULL
        WHERE sp.store_product_id = ANY(%s)"""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, (ids, ids)).fetchall()
    by_id = {r["store_product_id"]: r for r in rows}
    products = [by_id[i] for i in ids if i in by_id]   # порядок як передав клієнт

    # характеристики: union назв у порядку появи, значення вирівняні по колонках
    specs = {i: product_specs(conn, i) for i in ids if i in by_id}
    order, seen = [], set()
    for i in ids:
        sp = specs.get(i)
        if sp:
            for a in sp["attrs"]:
                if a["name"] not in seen:
                    seen.add(a["name"]); order.append(a["name"])
    spec_rows = []
    for name in order:
        values = []
        for i in ids:
            if i not in by_id:
                continue
            sp = specs.get(i)
            val = next((a["value"] for a in sp["attrs"] if a["name"] == name), None) if sp else None
            values.append(val)
        spec_rows.append({"name": name, "values": values})
    return {"products": products, "spec_rows": spec_rows}


def product_offers(conn, store_product_id: int):
    """«Де купити» (T15/§17.5): ПО ОДНІЙ (найдешевшій) пропозиції на КРАМНИЦЮ з тим
    самим товаром (однаковий match_key: GTIN або артикул), сортовано від найдешевшої.
    Включає сам товар.

    Дедуп по крамниці (не по товару): родовий артикул (OPPO CPH2801, Motorola PBA…)
    спільний для кольорових варіантів → без дедупу «Де купити» двічі писало б ту саму
    крамницю. Товар без ключа → [] (нема на чому групувати). Ціна — з СИРОГО
    price_snapshot (оффер крамниці існує й без активної знижки).
    """
    sql = """
        WITH grp AS (
            SELECT sp.store_product_id, sp.source_id, sp.title, sp.url, s.name AS store,
                   (sp.title ~* %s) AS is_used
            FROM store_product sp
            JOIN source s USING (source_id)
            WHERE sp.match_key IS NOT NULL
              AND sp.match_key = (SELECT match_key FROM store_product WHERE store_product_id = %s)
        ),
        last_price AS (
            SELECT DISTINCT ON (ps.store_product_id)
                   ps.store_product_id, ps.price_now_kop, ps.price_old_kop, ps.in_stock,
                   (ps.seen_at AT TIME ZONE 'Europe/Kyiv')::date AS seen_day
            FROM price_snapshot ps
            JOIN grp USING (store_product_id)
            ORDER BY ps.store_product_id, ps.seen_at DESC
        ),
        joined AS (
            SELECT g.source_id, g.store_product_id, g.store, g.title, g.url, g.is_used,
                   lp.price_now_kop AS current_kop, lp.price_old_kop AS old_declared_kop,
                   lp.in_stock, lp.seen_day
            FROM grp g JOIN last_price lp USING (store_product_id)
        ),
        per_store AS (   -- одна пропозиція на крамницю: в наявності → ЧИСТА → найдешевша
            -- `is_used` перед ціною свідомо: якщо крамниця продає і новий, і уцінений,
            -- порівнювати треба новий — інакше її «ціна» в списку виявиться ціною
            -- відкритої коробки, і порівняння перестає бути однорідним.
            SELECT DISTINCT ON (source_id) store_product_id, store, title, url,
                   current_kop, old_declared_kop, in_stock, seen_day, is_used
            FROM joined
            ORDER BY source_id, in_stock DESC, is_used, current_kop
        )
        SELECT store_product_id, store, title, url, current_kop, old_declared_kop,
               in_stock, seen_day, is_used
        -- Сортуємо за ціною, а уцінене НЕ ховаємо: пропозиція справжня й купувана,
        -- людина має право її бачити. Але мусить знати, що це інший стан, — тому
        -- прапорець їде на клієнт і малюється позначкою.
        FROM per_store ORDER BY current_kop, store"""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (_USED_RE, store_product_id)).fetchall()


# Товари, які не можуть бути обличчям категорії: інший стан (уцінка/відновлене) або
# взагалі не той товар (комплект/набір — у нього спільний артикул із самим ТВ).
_TILE_SKIP_RE = _USED_RE + r'|комплект|набір|набор'

# Перевага за розміром фото. Заміряно 2026-07-21 (по одному ТВ-фото з кожної крамниці):
#   Comfy 1307x880 · Brain 700x700 · Rozetka 400x264 · Foxtrot 220x220 · Moyo 200x128
#   · Citrus 180x119 (1.1 КБ — на плитці шириною ~380 px це мило)
# Крамниці поза списком — у кінець: краще відоме дрібне, ніж невідоме.
_TILE_SOURCE_RANK = {"Comfy": 0, "Brain": 0, "Rozetka": 1, "Foxtrot": 2, "Moyo": 2, "Citrus": 3}


def _nice_kop(kop: float) -> int:
    """Округлити копійки до «гарної» цінової межі: 1/1.5/2/3/5/7 × 10^k гривень.
    2 149 900 коп (21 499 грн) → 2 000 000 (20 000 грн)."""
    grn = max(float(kop) / 100.0, 1.0)
    exp = 10 ** math.floor(math.log10(grn))
    best = min((m * exp for m in (1, 1.5, 2, 3, 5, 7, 10)), key=lambda v: abs(v - grn))
    return int(round(best * 100))


def categories(conn):
    """Лише категорії з активними знижками (+ лічильник) — для селектора §9.1 та
    сітки-каталогу §17. Порожні (без знижок) НЕ повертаємо. Кожну збагачуємо розділом
    і іконкою (taxonomy.category_ui); сортуємо за розділом, тоді за к-стю (більше — вище)."""
    # image_url — фото товару-представника. Це ВКАЗІВНИК (hotlink), байти не зберігаємо (§7.4).
    #
    # Було «найбільша знижка в категорії» — і це давало три вади одразу:
    #   1) НЕСТАБІЛЬНІСТЬ: обличчя категорії стрибало щоразу, коли мінялись знижки;
    #   2) УЦІНКА: 2026-07-21 плитку «Телевізори» очолював уцінений Samsung;
    #   3) БАНЕРИ: найгучніші акції мають найбільше маркетингу у фото, тобто правило
    #      системно обирало саме рекламні картинки.
    # Тепер: спершу крамниці з великими фото, тоді канонічність (скільки крамниць
    # продають цю модель), тоді стабільний tie-break по id.
    #
    # ЧОГО ЦЕ НЕ ЛІКУЄ: рекламний напис ЗАПЕЧЕНИЙ у саму картинку (телевізор на фото
    # показує «ЛІТНІЙ СЕЙЛ −30%»). Заміряно: таке фото трапилось у Rozetka, а чисте —
    # у Brain, тобто від крамниці не залежить. Визначити це з метаданих неможливо,
    # потрібен аналіз пікселів — свідомо не робимо (§7.4: чужих байтів не тягнемо).
    ranks = _TILE_SOURCE_RANK
    order_rank = " ".join(f"WHEN '{k}' THEN {v}" for k, v in ranks.items())
    sql = f"""
        WITH cnt AS (
            SELECT c.category_id, c.slug, c.name, count(*) AS n
            FROM category c
            JOIN store_product sp ON sp.category_id = c.category_id
            JOIN discount_event de ON de.store_product_id = sp.store_product_id
            WHERE de.ended_at IS NULL
            GROUP BY c.category_id, c.slug, c.name
        ),
        grp AS (   -- канонічність моделі: скільки РІЗНИХ крамниць її продають
            SELECT match_key, count(DISTINCT source_id) AS stores
            FROM store_product WHERE match_key IS NOT NULL GROUP BY match_key
        ),
        price AS (  -- остання ціна кожного знижкового товару → терцілі категорії
            SELECT sp.category_id, lp.price_now_kop
            FROM (SELECT DISTINCT store_product_id FROM discount_event
                  WHERE ended_at IS NULL) de
            JOIN store_product sp USING (store_product_id)
            JOIN LATERAL (
                SELECT ps.price_now_kop FROM price_snapshot ps
                WHERE ps.store_product_id = sp.store_product_id
                ORDER BY ps.seen_at DESC LIMIT 1
            ) lp ON TRUE
        ),
        pct AS (
            SELECT category_id,
                   percentile_cont(0.33) WITHIN GROUP (ORDER BY price_now_kop) AS p33,
                   percentile_cont(0.66) WITHIN GROUP (ORDER BY price_now_kop) AS p66
            FROM price GROUP BY category_id
        ),
        pic AS (
            -- обличчя категорії ОДНИМ проходом (DISTINCT ON), не LATERAL-ом на кожну:
            -- 137 категорій × скан-сорт знижкових товарів давали 8 с на /api/categories
            -- (впіймано 2026-07-24 за скаргою на затримки). Порядок вибору той самий:
            -- крамниці з великими фото → канонічність моделі → стабільний id.
            SELECT DISTINCT ON (sp.category_id) sp.category_id, sp.image_url
            FROM store_product sp
            JOIN source s USING (source_id)
            JOIN (SELECT DISTINCT store_product_id FROM discount_event
                  WHERE ended_at IS NULL) de ON de.store_product_id = sp.store_product_id
            LEFT JOIN grp g ON g.match_key = sp.match_key
            WHERE sp.image_url IS NOT NULL
              AND sp.title !~* %s
            ORDER BY sp.category_id,
                     CASE s.name {order_rank} ELSE 9 END,
                     COALESCE(g.stores, 1) DESC,
                     sp.store_product_id
        )
        SELECT cnt.slug, cnt.name, cnt.n, pic.image_url, pct.p33, pct.p66
        FROM cnt
        LEFT JOIN pct ON pct.category_id = cnt.category_id
        LEFT JOIN pic ON pic.category_id = cnt.category_id"""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, (_TILE_SKIP_RE,)).fetchall()
    for r in rows:
        r["section"], r["icon"] = category_ui(r["slug"])
        # цінові межі КАТЕГОРІЇ для фільтра (§17-nav): терцілі реальних цін,
        # округлені до «гарних» гривень. Глобальні діапазони («до 500 ₴» у
        # ноутбуках) були декоративні. Мало товарів або межі злиплись → null,
        # клієнт відкотиться до глобального списку.
        p33, p66 = r.pop("p33", None), r.pop("p66", None)
        lo = _nice_kop(p33) if p33 is not None and r["n"] >= 12 else None
        hi = _nice_kop(p66) if p66 is not None and r["n"] >= 12 else None
        if lo is not None and hi is not None and lo < hi:
            r["p33_kop"], r["p66_kop"] = lo, hi
        else:
            r["p33_kop"] = r["p66_kop"] = None
    rows.sort(key=lambda r: (SECTION_ORDER.get(r["section"], 9), -r["n"], r["name"]))
    return rows


def add_watchlist(conn, tg_user_id: int, kind: str, ref_id: int | None, query_text: str | None):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "INSERT INTO watchlist (tg_user_id, kind, ref_id, query_text) VALUES (%s,%s,%s,%s) "
            "RETURNING watchlist_id, kind, ref_id, query_text",
            (tg_user_id, kind, ref_id, query_text)).fetchone()


def list_watchlist(conn, tg_user_id: int):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT watchlist_id, kind, ref_id, query_text, created_at FROM watchlist "
            "WHERE tg_user_id = %s ORDER BY created_at DESC", (tg_user_id,)).fetchall()


# ── акаунти (S11) ────────────────────────────────────────────────────────────────
def create_user(conn, email: str, password_hash: str):
    """Створює юзера. Повертає (user_id, role) або None, якщо email зайнятий."""
    try:
        return conn.execute(
            "INSERT INTO app_user (email, password_hash) VALUES (%s,%s) "
            "RETURNING user_id, role", (email, password_hash)).fetchone()
    except errors.UniqueViolation:
        return None


def get_user_by_email(conn, email: str):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT user_id, email, password_hash, role, email_verified, is_active "
            "FROM app_user WHERE lower(email) = lower(%s)", (email,)).fetchone()


def touch_login(conn, user_id: int):
    conn.execute("UPDATE app_user SET last_login_at = now() WHERE user_id = %s", (user_id,))


def get_user(conn, user_id: int):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT user_id, email, role, created_at, email_verified, is_active, "
            "       email_alerts "
            "FROM app_user WHERE user_id = %s", (user_id,)).fetchone()


# ── коди підтвердження / скидання пароля (S13) ────────────────────────────────────
def create_token(conn, user_id: int, kind: str, code_hash: str, ttl_s: int) -> None:
    """Новий одноразовий код. Старі невикористані токени ТОГО САМОГО виду гасимо
    (used_at=now): свіжий запит робить попередній код недійсним — інакше в пошті
    гуляло б кілька живих кодів на один акаунт."""
    conn.execute(
        "UPDATE account_token SET used_at = now() "
        "WHERE user_id = %s AND kind = %s AND used_at IS NULL", (user_id, kind))
    conn.execute(
        "INSERT INTO account_token (user_id, kind, code_hash, expires_at) "
        "VALUES (%s,%s,%s, now() + make_interval(secs => %s))",
        (user_id, kind, code_hash, ttl_s))


# Скільки невдалих спроб витримує ОДИН код, перш ніж згасне. П'ять — бо чесний
# користувач має код перед очима; це не про зручність, а про те, щоб перебір не
# масштабувався разом із числом IP у зловмисника (ревʼю безпеки 2026-07-26).
MAX_CODE_ATTEMPTS = 5


def consume_token(conn, user_id: int, kind: str, code_hash: str) -> bool:
    """Атомарно спожити код: активний (не-used, не-expired, збіг хешу) → позначити
    used, повернути True. Інакше False. RETURNING гарантує, що два паралельні запити
    не спожиють той самий код двічі.

    ⚠ Невдала спроба ВИТРАЧАЄ спробу самого коду. Доти ліміт стояв лише на IP, тож
    перебір 6-значного коду масштабувався разом із числом адрес. Тепер після
    MAX_CODE_ATTEMPTS промахів код гасне незалежно від того, звідки їх робили."""
    row = conn.execute(
        "UPDATE account_token SET used_at = now() "
        "WHERE token_id = (SELECT token_id FROM account_token "
        "                  WHERE user_id = %s AND kind = %s AND code_hash = %s "
        "                    AND used_at IS NULL AND expires_at > now() "
        "                  ORDER BY created_at DESC LIMIT 1) "
        "RETURNING token_id", (user_id, kind, code_hash)).fetchone()
    if row is not None:
        return True

    # промах: рахуємо його НАЙСВІЖІШОМУ активному коду цього юзера й кінця, а на
    # межі — гасимо код. Гасимо саме тут, одним запитом, щоб між перевіркою і
    # погашенням не було вікна для паралельних спроб.
    conn.execute(
        "UPDATE account_token "
        "SET attempts = attempts + 1, "
        "    used_at = CASE WHEN attempts + 1 >= %s THEN now() ELSE used_at END "
        "WHERE token_id = (SELECT token_id FROM account_token "
        "                  WHERE user_id = %s AND kind = %s "
        "                    AND used_at IS NULL AND expires_at > now() "
        "                  ORDER BY created_at DESC LIMIT 1)",
        (MAX_CODE_ATTEMPTS, user_id, kind))
    # ⚠ КОМІТ ОБОВʼЯЗКОВИЙ І НЕОЧЕВИДНИЙ. Викликач після False кидає HTTPException, а
    # пул на виході з винятком робить ROLLBACK — разом із ним відкочувався б і лічильник,
    # тобто захист від перебору мовчки не працював би зовсім. Спіймано тестом 2026-07-26:
    # код не гаснув після п'яти промахів. Лічильник промахів — це аудит спроби, а не
    # частина бізнес-транзакції, тож він мусить пережити її відкат.
    conn.commit()
    return False


def set_email_verified(conn, user_id: int) -> None:
    conn.execute("UPDATE app_user SET email_verified = true WHERE user_id = %s", (user_id,))


# ── адмін-функції під ролями (S15) + панель (S16) ─────────────────────────────────
_ROLES = ("user", "collector", "moderator", "admin")
USERS_PER_PAGE = 50
_BADGE_ORDER = ("verified", "verified_provisional", "pumped",
                "declared", "insufficient_history")


class AdminError(Exception):
    """Порушення правила/безпеки адмін-дії (self-lockout, останній admin тощо) → 400."""


class AdminForbidden(AdminError):
    """Межа прав: актор пройшов гейт, але ця дія над цією ціллю йому заборонена → 403."""


def _audit(conn, actor_id: int, action: str, target_id: int | None, detail: str) -> None:
    """Слід адмін-дії. Email денормалізуємо ЗНІМКОМ (0171): акаунт можуть видалити, а
    журнал мусить лишитись читабельним — інакше після видалення слід перетворюється
    на пару беззмістовних чисел."""
    conn.execute(
        "INSERT INTO admin_audit (actor_id, action, target_id, detail, actor_email, target_email) "
        "VALUES (%s,%s,%s,%s, (SELECT email FROM app_user WHERE user_id = %s), "
        "        (SELECT email FROM app_user WHERE user_id = %s))",
        (actor_id, action, target_id, detail, actor_id, target_id))


def audit_action(conn, actor_id: int, action: str, target_id: int | None,
                 detail: str) -> None:
    """Публічний вхід у журнал для дій, які виконує шар API сам (напр. надсилання
    листа): сама дія живе в main.py, але слід має лягати тим самим шляхом."""
    _audit(conn, actor_id, action, target_id, detail)


def list_audit(conn, action: str | None = None, page: int = 0,
               per_page: int = USERS_PER_PAGE) -> dict:
    """Журнал адмін-дій (S16 П3). До нього `admin_audit` була write-only: слід писався,
    прочитати його не було чим — тобто перевірити, хто роздав права, було неможливо."""
    per_page = max(1, min(int(per_page or USERS_PER_PAGE), 200))
    page = max(0, int(page or 0))
    where, params = [], []
    if action:
        where.append("action = %s")
        params.append(action)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT audit_id, actor_id, actor_email, action, target_id, target_email, "
            "       detail, created_at FROM admin_audit" + clause +
            " ORDER BY created_at DESC, audit_id DESC LIMIT %s OFFSET %s",
            params + [per_page, page * per_page]).fetchall()
        total = cur.execute("SELECT count(*) AS n FROM admin_audit" + clause,
                            params).fetchone()["n"]
    return {"entries": rows, "total": total, "page": page, "per_page": per_page,
            "pages": (total + per_page - 1) // per_page}


def user_detail(conn, user_id: int) -> dict | None:
    """Картка акаунта: профіль + стеження + історія адмін-дій НАД НИМ. Один запит на
    блок — панель відкривається однією відповіддю, без N+1 з боку клієнта."""
    with conn.cursor(row_factory=dict_row) as cur:
        u = cur.execute(
            "SELECT user_id, email, role, is_active, email_verified, created_at, last_login_at "
            "FROM app_user WHERE user_id = %s", (user_id,)).fetchone()
        if u is None:
            return None
        u["watchlist"] = cur.execute(
            "SELECT watchlist_id, kind, ref_id, query_text, created_at FROM watchlist "
            "WHERE user_id = %s ORDER BY created_at DESC LIMIT 50", (user_id,)).fetchall()
        u["audit"] = cur.execute(
            "SELECT audit_id, actor_email, action, detail, created_at FROM admin_audit "
            "WHERE target_id = %s ORDER BY created_at DESC LIMIT 50", (user_id,)).fetchall()
    return u


def list_users(conn, q: str | None = None, role: str | None = None,
               active: bool | None = None, page: int = 0,
               per_page: int = USERS_PER_PAGE) -> dict:
    """Сторінка акаунтів із пошуком/фільтрами (S16). Пошук — ILIKE за email через
    ПАРАМЕТР (значення ніколи не склеюється в текст запиту). Пагінація обов'язкова:
    без неї список ріс би без межі й панель лягла б на тисячі акаунтів."""
    per_page = max(1, min(int(per_page or USERS_PER_PAGE), 200))
    page = max(0, int(page or 0))
    where, params = [], []
    if q:
        where.append("u.email ILIKE %s")
        params.append(f"%{q}%")
    if role:
        where.append("u.role = %s")
        params.append(role)
    if active is not None:
        where.append("u.is_active = %s")
        params.append(bool(active))
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT u.user_id, u.email, u.role, u.is_active, u.email_verified, "
            "       u.created_at, u.last_login_at, "
            "       (SELECT count(*) FROM watchlist w WHERE w.user_id = u.user_id) AS watchlist_n "
            "FROM app_user u" + clause +
            " ORDER BY u.created_at DESC LIMIT %s OFFSET %s",
            params + [per_page, page * per_page]).fetchall()
        total = cur.execute("SELECT count(*) AS n FROM app_user u" + clause,
                            params).fetchone()["n"]
    return {"users": rows, "total": total, "page": page, "per_page": per_page,
            "pages": (total + per_page - 1) // per_page}


def admin_metrics(conn) -> dict:
    """Метрики панелі (S16): дані · детекція · збір по крамницях · акаунти.

    Панель мусить показувати здоров'я ПРОДУКТУ, не лише акаунти: скільки товарів і
    цінової історії зібрано, що показала детекція (скільки накачаних знижок знайдено)
    і які крамниці мовчать. До S16 не було видно нічого з цього.

    ⚠ Нульові бейджі НЕ ховаємо: `verified 0` при 29 `pumped` — це сигнал, а не
    порожнеча (guardrail §7 брифа; тихий нуль — визнаний дефект показників)."""
    with conn.cursor(row_factory=dict_row) as cur:
        data = cur.execute(
            "SELECT (SELECT count(*) FROM store_product) AS products, "
            "       (SELECT count(*) FROM price_snapshot) AS snapshots, "
            "       (SELECT count(*) FROM discount_event) AS events, "
            "       (SELECT count(*) FROM category) AS categories, "
            "       (SELECT count(*) FROM source WHERE active) AS sources, "
            "       (SELECT count(*) FROM store_product "
            "          WHERE first_seen_at > now() - interval '1 day') AS products_1d, "
            "       (SELECT count(*) FROM price_snapshot "
            "          WHERE seen_at > now() - interval '1 day') AS snapshots_1d"
        ).fetchone()
        seen = {r["badge_state"]: r for r in cur.execute(
            "SELECT badge_state, count(*) AS total, "
            "       count(*) FILTER (WHERE computed_at > now() - interval '7 days') AS d7 "
            "FROM discount_event GROUP BY badge_state").fetchall()}
        accounts = cur.execute(
            "SELECT count(*) AS total, "
            "       count(*) FILTER (WHERE email_verified) AS verified, "
            "       count(*) FILTER (WHERE NOT is_active) AS banned, "
            "       count(*) FILTER (WHERE created_at > now() - interval '7 days') AS reg_7d, "
            "       count(*) FILTER (WHERE created_at > now() - interval '30 days') AS reg_30d, "
            "       count(*) FILTER (WHERE last_login_at > now() - interval '7 days') AS active_7d, "
            "       count(*) FILTER (WHERE last_login_at > now() - interval '30 days') AS active_30d "
            "FROM app_user").fetchone()
        by_role = {r["role"]: r["n"] for r in cur.execute(
            "SELECT role, count(*) AS n FROM app_user GROUP BY role").fetchall()}
        # starts_with, а не LIKE із шаблоном: у тексті запиту не має бути жодного «%»
        # крім плейсхолдера — psycopg сканує весь текст (test_sqlsafe, обпеклись 2026-07-21)
        stores = cur.execute(
            "SELECT source, count(*) AS tasks, "
            "       count(*) FILTER (WHERE last_status = 'ok') AS ok, "
            "       count(*) FILTER (WHERE starts_with(last_status, 'fail')) AS fail, "
            "       count(*) FILTER (WHERE fail_count > 0) AS failing, "
            "       round(EXTRACT(epoch FROM now() - "
            "             max(last_done_at) FILTER (WHERE last_status = 'ok')) / 60)::int AS ok_min "
            "FROM collect_task GROUP BY source ORDER BY source").fetchall()
    badges = [{"state": s,
               "total": seen.get(s, {}).get("total", 0),
               "d7": seen.get(s, {}).get("d7", 0)} for s in _BADGE_ORDER]
    accounts["by_role"] = by_role
    return {"data": data, "detection": {"badges": badges}, "accounts": accounts,
            "collect": {"stores": stores, **freshness(conn)}}


def _active_admin_count(conn, exclude_id: int | None = None) -> int:
    return conn.execute(
        "SELECT count(*) FROM app_user WHERE role='admin' AND is_active "
        "AND (%s::bigint IS NULL OR user_id <> %s)", (exclude_id, exclude_id)).fetchone()[0]


def set_user_role(conn, actor_id: int, target_id: int, new_role: str) -> dict:
    """Змінити роль (ЛИШЕ admin). Захисти: валідна роль; НЕ власна роль (анти-lockout);
    не знизити останнього активного admin. Пише аудит. Кидає AdminError на порушення."""
    if new_role not in _ROLES:
        raise AdminError(f"невідома роль (дозволені: {', '.join(_ROLES)})")
    if actor_id == target_id:
        raise AdminError("не можна змінювати власну роль")
    with conn.cursor(row_factory=dict_row) as cur:
        t = cur.execute("SELECT user_id, role, is_active FROM app_user WHERE user_id=%s",
                        (target_id,)).fetchone()
    if t is None:
        raise AdminError("акаунт не існує")
    if t["role"] == "admin" and new_role != "admin" and _active_admin_count(conn, target_id) == 0:
        raise AdminError("не можна лишити систему без активного адміна")
    conn.execute("UPDATE app_user SET role=%s WHERE user_id=%s", (new_role, target_id))
    _audit(conn, actor_id, "set_role", target_id, f"{t['role']}→{new_role}")
    return {"user_id": target_id, "role": new_role}


def set_user_active(conn, actor_id: int, actor_role: str, target_id: int, active: bool) -> dict:
    """Бан/розбан (moderator+). Захисти: не себе; moderator НЕ чіпає admin/moderator;
    не забанити останнього активного admin. Аудит."""
    if actor_id == target_id:
        raise AdminError("не можна банити себе")
    with conn.cursor(row_factory=dict_row) as cur:
        t = cur.execute("SELECT user_id, role, is_active FROM app_user WHERE user_id=%s",
                        (target_id,)).fetchone()
    if t is None:
        raise AdminError("акаунт не існує")
    if actor_role == "moderator" and t["role"] in ("admin", "moderator"):
        raise AdminForbidden("модератор не може банити адмінів/модераторів")
    if not active and t["role"] == "admin" and _active_admin_count(conn, target_id) == 0:
        raise AdminError("не можна забанити останнього активного адміна")
    conn.execute("UPDATE app_user SET is_active=%s WHERE user_id=%s", (active, target_id))
    _audit(conn, actor_id, "set_active", target_id, f"active={active}")
    return {"user_id": target_id, "is_active": active}


def admin_verify_email(conn, actor_id: int, target_id: int) -> dict:
    """Підтвердити email вручну (S16 П4) — підтримка, коли лист не доходить. Обхід
    поштової перевірки мусить лишати слід, тому обов'язково в аудит."""
    with conn.cursor(row_factory=dict_row) as cur:
        t = cur.execute("SELECT user_id, email, email_verified FROM app_user WHERE user_id=%s",
                        (target_id,)).fetchone()
    if t is None:
        raise AdminError("акаунт не існує")
    if t["email_verified"]:
        return {"user_id": target_id, "email_verified": True}   # нема що робити
    set_email_verified(conn, target_id)
    _audit(conn, actor_id, "verify_email", target_id, "підтверджено вручну")
    return {"user_id": target_id, "email_verified": True}


def delete_user(conn, actor_id: int, target_id: int) -> dict:
    """Видалити акаунт (S16 П4, ЛИШЕ admin) — незворотно, право на забуття.
    Захисти ті самі, що й у бану: не себе, не останнього активного admin.
    Watchlist і токени підуть каскадом; слід у журналі ЛИШИТЬСЯ (0171 денормалізував
    email), тож видалення акаунта не стирає історію того, хто роздавав права."""
    if actor_id == target_id:
        raise AdminError("не можна видалити власний акаунт")
    with conn.cursor(row_factory=dict_row) as cur:
        t = cur.execute("SELECT user_id, email, role FROM app_user WHERE user_id=%s",
                        (target_id,)).fetchone()
    if t is None:
        raise AdminError("акаунт не існує")
    if t["role"] == "admin" and _active_admin_count(conn, target_id) == 0:
        raise AdminError("не можна видалити останнього активного адміна")
    # аудит ПЕРЕД видаленням: інакше знімок email уже не з чого взяти
    _audit(conn, actor_id, "delete_user", target_id, f"видалено акаунт {t['email']}")
    conn.execute("DELETE FROM app_user WHERE user_id = %s", (target_id,))
    return {"deleted": target_id, "email": t["email"]}


def update_password(conn, user_id: int, password_hash: str) -> None:
    """Змінити пароль. Заодно гасимо всі невикористані reset-токени юзера — після
    зміни жоден старий код скидання не має лишитись живим."""
    conn.execute("UPDATE app_user SET password_hash = %s WHERE user_id = %s",
                 (password_hash, user_id))
    conn.execute("UPDATE account_token SET used_at = now() "
                 "WHERE user_id = %s AND kind = 'reset' AND used_at IS NULL", (user_id,))


# watchlist на app-юзера (окремо від Telegram-версії вище)
def add_watchlist_user(conn, user_id: int, kind: str, ref_id: int | None,
                       query_text: str | None, target_kop: int | None = None):
    """Додає у відстеження. Для товару СЕРВЕР сам фіксує поточну ціну (`price_at_add_kop`)
    з останнього снапшота — клієнт її не диктує, інакше можна було б намалювати неіснуючу
    економію (§7.5). Повторне додавання того самого товару НЕ дублюємо."""
    with conn.cursor(row_factory=dict_row) as cur:
        if kind == "store_product" and ref_id is not None:
            dup = cur.execute(
                "SELECT watchlist_id, kind, ref_id, query_text, price_at_add_kop FROM watchlist "
                "WHERE user_id = %s AND kind = 'store_product' AND ref_id = %s",
                (user_id, ref_id)).fetchone()
            if dup:
                return dup
        if kind in ("category", "query") and query_text:
            dup = cur.execute(
                "SELECT watchlist_id, kind, ref_id, query_text, price_at_add_kop FROM watchlist "
                "WHERE user_id = %s AND kind = %s AND query_text = %s",
                (user_id, kind, query_text)).fetchone()
            if dup:
                return dup
        price = None
        if kind == "store_product" and ref_id is not None:
            row = cur.execute(
                "SELECT price_now_kop FROM price_snapshot WHERE store_product_id = %s "
                "ORDER BY seen_at DESC LIMIT 1", (ref_id,)).fetchone()
            price = row["price_now_kop"] if row else None
        return cur.execute(
            "INSERT INTO watchlist (user_id, kind, ref_id, query_text, price_at_add_kop,"
            "                       target_kop) "
            "VALUES (%s,%s,%s,%s,%s,%s) "
            "RETURNING watchlist_id, kind, ref_id, query_text, price_at_add_kop, target_kop",
            (user_id, kind, ref_id, query_text, price, target_kop)).fetchone()


def remove_watchlist_user(conn, user_id: int, watchlist_id: int) -> bool:
    """Прибрати зі стеження. Чужий рядок не видалиться — user_id у WHERE."""
    row = conn.execute(
        "DELETE FROM watchlist WHERE watchlist_id = %s AND user_id = %s RETURNING watchlist_id",
        (watchlist_id, user_id)).fetchone()
    return row is not None


def list_price_drops(conn, user_id: int):
    """Відстежувані товари, що ПОДЕШЕВШАЛИ від часу, про який користувачеві вже казали.

    Точка відліку — `last_notified_kop`, а якщо ще не повідомляли, то ціна додавання.
    Тому повторне зниження дасть нове сповіщення, а те саме — ні (інакше телефон
    дзвонив би щогодини про одну й ту саму знижку).
    """
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (ps.store_product_id)
                   ps.store_product_id, ps.price_now_kop
            FROM price_snapshot ps
            JOIN watchlist w ON w.ref_id = ps.store_product_id
                            AND w.user_id = %s AND w.kind = 'store_product'
            ORDER BY ps.store_product_id, ps.seen_at DESC
        )
        SELECT w.watchlist_id, w.ref_id, sp.title, sp.url, sp.image_url,
               l.price_now_kop AS current_kop,
               COALESCE(w.last_notified_kop, w.price_at_add_kop) AS baseline_kop,
               (COALESCE(w.last_notified_kop, w.price_at_add_kop) - l.price_now_kop) AS drop_kop
        FROM watchlist w
        JOIN store_product sp ON sp.store_product_id = w.ref_id
        JOIN latest l ON l.store_product_id = w.ref_id
        WHERE w.user_id = %s AND w.kind = 'store_product'
          AND COALESCE(w.last_notified_kop, w.price_at_add_kop) IS NOT NULL
          AND l.price_now_kop < COALESCE(w.last_notified_kop, w.price_at_add_kop)
          -- Цільова ціна (S29): якщо вона задана, зниження саме по собі ще не привід —
          -- людина просила сказати, коли ціна ДІЙДЕ до її числа, а не коли просто впаде.
          AND (w.target_kop IS NULL OR l.price_now_kop <= w.target_kop)
        ORDER BY drop_kop DESC"""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (user_id, user_id)).fetchall()


def ack_price_drops(conn, user_id: int, watchlist_ids: list[int]) -> int:
    """Позначити, що про ці зниження вже повідомлено: `last_notified_kop` = поточна ціна.
    Чужі рядки не зачепить (user_id у WHERE). Повертає к-сть оновлених."""
    if not watchlist_ids:
        return 0
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (ps.store_product_id)
                   ps.store_product_id, ps.price_now_kop
            FROM price_snapshot ps
            JOIN watchlist w ON w.ref_id = ps.store_product_id AND w.user_id = %s
            ORDER BY ps.store_product_id, ps.seen_at DESC
        )
        -- last_notified_at ставимо ТУТ ЖЕ (S29): досі його писав лише ack категорій,
        -- тож для стеження за товаром колонка лишалась порожньою — і будь-який
        -- запобіжник частоти листів спирався б на порожнечу.
        UPDATE watchlist w SET last_notified_kop = l.price_now_kop, last_notified_at = now()
        FROM latest l
        WHERE w.ref_id = l.store_product_id
          AND w.user_id = %s AND w.watchlist_id = ANY(%s)
        RETURNING w.watchlist_id"""
    return len(conn.execute(sql, (user_id, user_id, list(watchlist_ids))).fetchall())


def list_watchlist_user(conn, user_id: int):
    """Список стеження, збагачений даними товару: назва/фото/поточна ціна + скільки
    крамниць у групі. `delta_kop` = поточна − на момент додавання (відʼємна = подешевшало).
    Для kind='category'/'query' товарні поля порожні."""
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (ps.store_product_id)
                   ps.store_product_id, ps.price_now_kop
            FROM price_snapshot ps
            JOIN watchlist w ON w.ref_id = ps.store_product_id
                            AND w.user_id = %s AND w.kind = 'store_product'
            ORDER BY ps.store_product_id, ps.seen_at DESC
        )
        SELECT w.watchlist_id, w.kind, w.ref_id, w.query_text, w.created_at,
               w.price_at_add_kop, w.target_kop, sp.title, sp.url, sp.image_url,
               s.name AS store, l.price_now_kop AS current_kop,
               (l.price_now_kop - w.price_at_add_kop) AS delta_kop,
               CASE WHEN sp.match_key IS NULL THEN 1
                    ELSE (SELECT count(DISTINCT sp2.source_id)
                          FROM store_product sp2 WHERE sp2.match_key = sp.match_key)
               END AS offers_n
        FROM watchlist w
        LEFT JOIN store_product sp ON w.kind = 'store_product' AND sp.store_product_id = w.ref_id
        LEFT JOIN source s USING (source_id)
        LEFT JOIN latest l ON l.store_product_id = w.ref_id
        WHERE w.user_id = %s
        ORDER BY w.created_at DESC"""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, (user_id, user_id)).fetchall()
    # категорійні рядки: людська назва замість порожнього title (slug лишаємось
    # у query_text — клієнту треба обидва)
    slugs = {r["query_text"] for r in rows if r["kind"] == "category" and r["query_text"]}
    if slugs:
        names = dict(conn.execute(
            "SELECT slug, name FROM category WHERE slug = ANY(%s)", (list(slugs),)).fetchall())
        for r in rows:
            if r["kind"] == "category":
                r["title"] = names.get(r["query_text"], r["query_text"])
    return rows


def list_category_news(conn, user_id: int):
    """Відстежувані КАТЕГОРІЇ з новими знижками від часу останнього сповіщення.

    Водяний знак — `last_notified_at` (нема → created_at): рахуємо discount_event,
    ЩО З'ЯВИЛИСЬ (computed_at) після нього і досі активні. Групуємо в один рядок на
    категорію (одне сповіщення «N нових знижок, топ −X%», не N окремих)."""
    sql = """
        SELECT w.watchlist_id, w.query_text AS slug, c.name AS category,
               n.new_n, n.top_pct, n.top_title
        FROM watchlist w
        JOIN category c ON c.slug = w.query_text
        JOIN LATERAL (
            SELECT count(*)::int AS new_n,
                   max(de.declared_pct)::int AS top_pct,
                   (array_agg(sp.title ORDER BY de.declared_pct DESC NULLS LAST))[1] AS top_title
            FROM discount_event de
            JOIN store_product sp USING (store_product_id)
            WHERE sp.category_id = c.category_id
              AND de.ended_at IS NULL
              AND de.computed_at > COALESCE(w.last_notified_at, w.created_at)
        ) n ON n.new_n > 0
        WHERE w.user_id = %s AND w.kind = 'category'
        ORDER BY n.new_n DESC"""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (user_id,)).fetchall()


def ack_category_news(conn, user_id: int, watchlist_ids: list[int]) -> int:
    """Позначити, що про нові знижки категорії повідомлено (водяний знак = now()).
    Чужі рядки не зачепить (user_id у WHERE)."""
    if not watchlist_ids:
        return 0
    rows = conn.execute(
        "UPDATE watchlist SET last_notified_at = now() "
        "WHERE user_id = %s AND kind = 'category' AND watchlist_id = ANY(%s) "
        "RETURNING watchlist_id", (user_id, list(watchlist_ids))).fetchall()
    return len(rows)


def freshness(conn) -> dict:
    """Скільки хвилин тому востаннє УСПІШНО збирали ціни — чесна свіжість даних для
    шапки стрічки. Публічне і навмисно бідне: лише хвилини, без внутрішніх метрик
    черги (вони — за гейтом колектора в collect_health)."""
    row = conn.execute(
        "SELECT round(EXTRACT(epoch FROM now() - max(last_done_at)) / 60)::int "
        "FROM collect_task WHERE last_status = 'ok'").fetchone()
    return {"minutes": row[0] if row and row[0] is not None else None}


def sitemap_rows(conn, limit: int = 20000):
    """Категорії й товари для sitemap.xml (S25).

    Порядок товарів НЕ випадковий: спершу ті, де в нас є що сказати понад ціну —
    активна подія з бейджем. Сторінка товару без нашого вердикту показує те саме, що
    сторінка крамниці, тож у мапі вона нижча. Ліміт — бо мапа має стелю 50 000 URL,
    і роздувати її сторінками, які ні на що не відповідають, шкідливо для індексації."""
    cats = [r[0] for r in conn.execute(
        "SELECT DISTINCT c.slug FROM category c "
        "  JOIN store_product sp ON sp.category_id = c.category_id "
        "  JOIN discount_event de ON de.store_product_id = sp.store_product_id "
        " WHERE de.ended_at IS NULL ORDER BY c.slug").fetchall()]
    prods = [r[0] for r in conn.execute(
        "SELECT sp.store_product_id FROM store_product sp "
        "  LEFT JOIN discount_event de "
        "         ON de.store_product_id = sp.store_product_id AND de.ended_at IS NULL "
        " ORDER BY (de.badge_state IN ('verified','verified_provisional','pumped')) DESC NULLS LAST, "
        "          de.computed_at DESC NULLS LAST, sp.store_product_id DESC "
        " LIMIT %s", (limit,)).fetchall()]
    models = [r[0] for r in conn.execute(
        "SELECT p.product_id FROM product p "
        "  JOIN store_product sp ON sp.match_key = p.match_key "
        " GROUP BY p.product_id HAVING count(DISTINCT sp.source_id) >= 2 "
        " ORDER BY count(DISTINCT sp.source_id) DESC, p.product_id LIMIT 10000").fetchall()]
    return cats, prods, models


# ─────────────────────────── сторінки-обличчя (S27) ───────────────────────────
def category_meta(conn, slug: str):
    """Назва категорії + скільки в ній активних знижок — для <title> і опису сторінки.

    Потрібно саме серверу: до 2026-07-27 усі 148 адрес `?c=…` віддавали ОДИН заголовок
    і canonical на `/catalog`, тобто самі казали краулеру «я копія». Показувати число
    в описі теж не косметика — «12 знижок» проти «знижки» різнить сніпет у видачі."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT c.name, c.slug, count(de.discount_event_id)::int AS n "
            "  FROM category c "
            "  LEFT JOIN store_product sp ON sp.category_id = c.category_id "
            "  LEFT JOIN discount_event de ON de.store_product_id = sp.store_product_id "
            "                             AND de.ended_at IS NULL "
            " WHERE c.slug = %s GROUP BY c.name, c.slug", (slug,)).fetchone()


# Крамниці мають лише `name` (латиниця: Comfy, Rozetka…), окремої колонки slug у схемі
# немає. Тому адреса /store/comfy зіставляється з lower(name): стабільно, без міграції
# й без транслітерації, яка колись розійшлася б із назвою.
_STORE_FACTS = """
    SELECT s.source_id, s.name, s.base_url,
           count(DISTINCT sp.store_product_id)::int AS products,
           count(DISTINCT de.discount_event_id) FILTER (WHERE de.ended_at IS NULL)::int AS discounts,
           count(DISTINCT de.discount_event_id) FILTER (
             WHERE de.ended_at IS NULL
               AND de.badge_state IN ('verified','verified_provisional'))::int AS verified,
           count(DISTINCT de.discount_event_id) FILTER (
             WHERE de.ended_at IS NULL AND de.badge_state = 'pumped')::int AS pumped,
           max(sp.last_seen_at) AS last_seen
      FROM source s
      LEFT JOIN store_product sp ON sp.source_id = s.source_id
      LEFT JOIN discount_event de ON de.store_product_id = sp.store_product_id
"""


def store_list(conn):
    """Усі крамниці, за якими ми стежимо, з ФАКТАМИ — без жодного рейтингу.

    ⚠ Свідомо немає «частки накачаних» і сортування за нею: це був би вердикт про
    чесність крамниці, а видимий шар не оцінює (T12). Порядок — за кількістю знижок,
    тобто за нашим покриттям, а не за «поведінкою» крамниці."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(_STORE_FACTS +
                           " WHERE s.active GROUP BY s.source_id, s.name, s.base_url"
                           " ORDER BY discounts DESC, s.name").fetchall()
    for r in rows:
        r["slug"] = r["name"].lower()
    return rows


def store_meta(conn, slug: str):
    """Одна крамниця + її найбільші категорії (щоб було куди піти зі сторінки)."""
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(_STORE_FACTS +
                          " WHERE s.active AND lower(s.name) = %s"
                          " GROUP BY s.source_id, s.name, s.base_url"
                          " ORDER BY s.source_id LIMIT 1", (slug,)).fetchone()
        if row is None:
            return None
        row["slug"] = row["name"].lower()
        row["categories"] = cur.execute(
            "SELECT c.name, c.slug, count(*)::int AS n "
            "  FROM store_product sp JOIN category c ON c.category_id = sp.category_id "
            " WHERE sp.source_id = %s GROUP BY c.name, c.slug "
            " ORDER BY n DESC, c.name LIMIT 12", (row["source_id"],)).fetchall()
    return row


def delete_own_account(conn, user_id: int) -> dict:
    """Самостійне видалення акаунта — вимога Google Play (веб + шлях у застосунку).

    Окремо від `delete_user`, бо той НАВМИСНО забороняє видаляти себе: там це захист
    адміна від помилки. Тут навпаки — це право людини, і єдиний захист лишається один:
    останній активний адмін не може піти, інакше система лишиться без керування.
    Слід у журналі переживає видалення (0171 тримає знімок email)."""
    with conn.cursor(row_factory=dict_row) as cur:
        u = cur.execute("SELECT user_id, email, role FROM app_user WHERE user_id=%s",
                        (user_id,)).fetchone()
    if u is None:
        raise AdminError("акаунт не існує")
    if u["role"] == "admin" and _active_admin_count(conn, user_id) == 0:
        raise AdminError("ви єдиний активний адміністратор — спершу призначте іншого")
    _audit(conn, user_id, "delete_own_account", user_id,
           f"самостійне видалення акаунта {u['email']}")
    conn.execute("DELETE FROM app_user WHERE user_id = %s", (user_id,))
    return {"deleted": user_id}


# ─────────────────────── виміряні зниження цін (S28) ───────────────────────
# Наш ЄДИНИЙ актив, який неможливо підробити: знижку оголошує крамниця (її можна
# намалювати), а зниження ціни МІРЯЄМО МИ. До 2026-07-27 воно існувало лише
# персонально (watchlist), тобто вимагало реєстрації й ручного додавання товару.
#
# Порівнюємо останній вимір із останнім виміром ДО вікна — не з максимумом усередині.
# Максимум перебільшував би: «ціна впала на 40%», якщо всередині доби був стрибок.
# Товар, який ми вперше побачили всередині вікна, у видачу не потрапляє: сказати
# «подешевшав» про нього ми не маємо права — не було з чим порівнювати.
_MOVES_CTE = """
    WITH cur AS (
        SELECT DISTINCT ON (store_product_id)
               store_product_id, price_now_kop, seen_at, in_stock
          FROM price_snapshot
         WHERE seen_at > now() - make_interval(days => %s)
         ORDER BY store_product_id, seen_at DESC),
    prev AS (
        SELECT DISTINCT ON (ps.store_product_id)
               ps.store_product_id, ps.price_now_kop, ps.seen_at
          FROM price_snapshot ps
          JOIN cur c ON c.store_product_id = ps.store_product_id
         WHERE ps.seen_at <= now() - make_interval(days => %s)
         ORDER BY ps.store_product_id, ps.seen_at DESC)
"""

# Поріг 1 грн: рух на копійки — це не подія, а шум округлення в крамниці.
_MIN_DROP_KOP = 100


# ⚠ ПОРЯДОК ЗА ВІДСОТКОМ СТАВИТЬ АРТЕФАКТ ПЕРШИМ — заміряно 2026-07-28.
# Перша ж видача очолювалась «−86%: 3133 → 449 грн» на кормі. Перевірка історії
# показала три виміри тієї самої сторінки й стрибок у 7 разів: це майже напевно зміна
# фасування/варіанта на сторінці крамниці, а не зниження ціни (прапорець
# needs_variant_resolution на товарі НЕ стоїть, тож фільтром по ньому таке не спіймати).
# Розподіл підтверджує: 199 знижень у межах 10%, 42 до 20%, 10 до 30%, далі поодинокі —
# і один самотній на 86% із порожнечею між 50% і 80%. Класична ознака чужої популяції.
#
# Тому за замовчуванням сортуємо ЗА ЧАСОМ ВИМІРУ: сторінка обіцяє «що подешевшало», а
# не «найбільші знижки», і хронологія нікого не підіймає штучно. Поріг «понад скільки
# відсотків вважати артефактом» я НЕ вигадую: пороги — під людським ревʼю (інваріант C).
_DROP_ORDER = {
    "fresh": "cur.seen_at DESC, drop_pct DESC",
    "deep": "drop_pct DESC, drop_kop DESC",
}


def price_drops(conn, days: int = 1, limit: int = 50, offset: int = 0,
                order: str = "fresh"):
    """Товари, які за нашими вимірами ПОДЕШЕВШАЛИ."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(_MOVES_CTE + """
            SELECT sp.store_product_id, sp.title, sp.url, sp.image_url,
                   s.name AS store, c.name AS category, c.slug AS category_slug,
                   cur.price_now_kop AS current_kop, p.price_now_kop AS was_kop,
                   (p.price_now_kop - cur.price_now_kop) AS drop_kop,
                   round(100.0 * (p.price_now_kop - cur.price_now_kop)
                         / p.price_now_kop)::int AS drop_pct,
                   p.seen_at AS was_at, cur.seen_at AS now_at,
                   de.badge_state, pr.product_id,
                   (SELECT count(DISTINCT s2.source_id) FROM store_product s2
                     WHERE s2.match_key = sp.match_key) AS stores_n
              FROM cur
              JOIN prev p USING (store_product_id)
              JOIN store_product sp ON sp.store_product_id = cur.store_product_id
              JOIN source s USING (source_id)
              JOIN category c ON c.category_id = sp.category_id
              LEFT JOIN product pr ON pr.match_key = sp.match_key
              LEFT JOIN discount_event de ON de.store_product_id = sp.store_product_id
                                         AND de.ended_at IS NULL
             WHERE cur.in_stock
               AND cur.price_now_kop < p.price_now_kop
               AND p.price_now_kop - cur.price_now_kop >= %s
               -- ДЕДУПЛІКАЦІЯ ЗА МОДЕЛЛЮ (S30): той самий телефон у пʼяти крамницях
               -- давав пʼять рядків поспіль — фід виглядав як помилка. Лишаємо
               -- НАЙДЕШЕВШУ сторінку моделі; товари без ключа (майже половина бази)
               -- проходять як були — їх нема з чим групувати.
               -- ⚠ Без знака відсотка в тексті: psycopg сканує на плейсхолдери ВЕСЬ
               -- запит, включно з коментарями (див. test_sqlsafe).
               -- ⚠ Порівняння «ціна = мінімум» лишало ДВА рядки, коли дві сторінки
               -- моделі коштують однаково (той самий товар двічі в одній крамниці —
               -- заміряно на живому: XFX Quicksilver). Тому обираємо КОНКРЕТНИЙ рядок
               -- за (ціна, id), а не всі, що дорівнюють мінімуму.
               AND (sp.match_key IS NULL OR sp.store_product_id = (
                     SELECT s2.store_product_id FROM cur l2
                       JOIN store_product s2 ON s2.store_product_id = l2.store_product_id
                      WHERE s2.match_key = sp.match_key
                      ORDER BY l2.price_now_kop, s2.store_product_id LIMIT 1))
             ORDER BY """ + _DROP_ORDER.get(order, _DROP_ORDER["fresh"]) + """,
                      sp.store_product_id
             LIMIT %s OFFSET %s""",
            (days, days, _MIN_DROP_KOP, limit, offset)).fetchall()


def price_moves_summary(conn, days: int = 1):
    """Скільки подешевшало / подорожчало / скільки взагалі було з чим порівняти.

    Подорожчання показуємо НАВМИСНО: без нього сторінка читалась би як «усе дешевшає»,
    хоча за добу 27.07 ми бачили 258 знижень проти 658 підвищень. Це та сама чесність,
    що й «мовчимо, коли історії замало» — інакше ми б робили власну накачану знижку."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(_MOVES_CTE + """
            SELECT count(*) FILTER (WHERE cur.price_now_kop < p.price_now_kop
                                      AND p.price_now_kop - cur.price_now_kop >= %s)::int AS down,
                   count(*) FILTER (WHERE cur.price_now_kop > p.price_now_kop
                                      AND cur.price_now_kop - p.price_now_kop >= %s)::int AS up,
                   count(*)::int AS compared
              FROM cur JOIN prev p USING (store_product_id)
             WHERE cur.in_stock""",
            (days, days, _MIN_DROP_KOP, _MIN_DROP_KOP)).fetchone()


# ═══════════════════ цільова ціна, стеження за запитом, історичний мінімум (S29) ═══
def set_watch_target(conn, user_id: int, watchlist_id: int, target_kop: int | None):
    """Цільова ціна для стеження. NULL = сповіщати про будь-яке зниження (як було).

    Чужий рядок не зачепить — user_id у WHERE."""
    row = conn.execute(
        "UPDATE watchlist SET target_kop = %s WHERE watchlist_id = %s AND user_id = %s "
        "RETURNING watchlist_id, target_kop", (target_kop, watchlist_id, user_id)).fetchone()
    return None if row is None else {"watchlist_id": row[0], "target_kop": row[1]}


def query_watch_hits(conn, user_id: int | None = None):
    """Товари під стеженням ЗА ЗАПИТОМ, які впали до цільової ціни.

    ⚠ Стеження за запитом БЕЗ цілі не має сенсу й не обробляється: «повідом про
    будь-яке зниження серед усього, що підходить під слово „навушники“» — це не
    сповіщення, а розсилка. Ціль робить твердження перевірюваним: «дешевше за X».

    Памʼять про надіслане — `alert_sent` на пару (стеження, товар): наступний лист
    піде, лише якщо ціна впала ЩЕ нижче за ту, про яку вже казали."""
    # ⚠ Патерни залежать від тексту КОЖНОГО стеження, тож одним запитом їх не підставити:
    # ILIKE ANY(%s) вимагає масиву на рядок. Тому беремо стеження, а товари добираємо
    # по одному запиту на стеження — їх одиниці, а не тисячі.
    from search import search_patterns
    with conn.cursor(row_factory=dict_row) as cur:
        watches = cur.execute(
            "SELECT watchlist_id, user_id, query_text, target_kop FROM watchlist "
            " WHERE kind = 'query' AND target_kop IS NOT NULL AND user_id IS NOT NULL "
            "   AND (%s::bigint IS NULL OR user_id = %s)", (user_id, user_id)).fetchall()
        out = []
        for w in watches:
            pats = search_patterns(w["query_text"])
            if not pats:
                continue
            out.extend(cur.execute(
                "WITH latest AS ("
                "    SELECT DISTINCT ON (ps.store_product_id) ps.store_product_id, ps.price_now_kop"
                "      FROM price_snapshot ps"
                "     WHERE ps.store_product_id IN ("
                "           SELECT store_product_id FROM store_product WHERE title ILIKE ANY(%s))"
                "     ORDER BY ps.store_product_id, ps.seen_at DESC) "
                "SELECT %s::bigint AS watchlist_id, %s::bigint AS user_id, %s::text AS query_text,"
                "       %s::bigint AS target_kop,"
                "       sp.store_product_id, sp.title, sp.url, s.name AS store,"
                "       l.price_now_kop AS current_kop"
                "  FROM store_product sp"
                "  JOIN source s USING (source_id)"
                "  JOIN latest l ON l.store_product_id = sp.store_product_id"
                "  LEFT JOIN alert_sent a ON a.watchlist_id = %s"
                "                        AND a.store_product_id = sp.store_product_id"
                " WHERE sp.title ILIKE ANY(%s) AND l.price_now_kop <= %s"
                "   AND (a.price_kop IS NULL OR l.price_now_kop < a.price_kop)"
                " ORDER BY l.price_now_kop LIMIT 20",
                (pats, w["watchlist_id"], w["user_id"], w["query_text"], w["target_kop"],
                 w["watchlist_id"], pats, w["target_kop"])).fetchall())
        return out


def mark_alert_sent(conn, rows) -> int:
    """Запамʼятати, про що сповістили. UPSERT: наступного разу поріг — ця ціна."""
    n = 0
    for r in rows:
        conn.execute(
            "INSERT INTO alert_sent (watchlist_id, store_product_id, price_kop) "
            "VALUES (%s,%s,%s) "
            "ON CONFLICT (watchlist_id, store_product_id) "
            "DO UPDATE SET price_kop = EXCLUDED.price_kop, sent_at = now()",
            (r["watchlist_id"], r["store_product_id"], r["current_kop"]))
        n += 1
    return n


def historical_low(conn, store_product_id: int):
    """Найнижча ціна ЗА ЧАС НАШИХ СПОСТЕРЕЖЕНЬ + межі того часу.

    ⚠ Повертаємо не лише мінімум, а й `days`/`first_seen`: «найнижча за весь час» при
    десятиденній історії було б самообманом — тим самим, що ми ловимо в крамниць.
    Твердження мусить нести власне вікно, інакше воно не перевірюване (T12)."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT min(price_now_kop)::bigint AS low_kop,"
            "       (SELECT seen_at::date FROM price_snapshot"
            "         WHERE store_product_id = %s"
            "         ORDER BY price_now_kop, seen_at LIMIT 1) AS low_day,"
            "       min(seen_at)::date AS first_day, max(seen_at)::date AS last_day,"
            "       (max(seen_at)::date - min(seen_at)::date + 1) AS days,"
            "       count(*)::int AS measurements"
            "  FROM price_snapshot WHERE store_product_id = %s",
            (store_product_id, store_product_id)).fetchone()


def set_email_alerts(conn, user_id: int, enabled: bool) -> bool:
    """Згода на листи про зниження цін. Транзакційних (verify/reset) не стосується:
    ті — відповідь на дію людини, а не наша ініціатива."""
    row = conn.execute(
        "UPDATE app_user SET email_alerts = %s WHERE user_id = %s RETURNING user_id",
        (enabled, user_id)).fetchone()
    return row is not None


def users_for_alerts(conn):
    """Кому взагалі можна писати про ціни: підтверджена пошта, згода, активний акаунт.

    Непідтверджена пошта — навмисно ні: писати на адресу, яку людина не підтвердила,
    означає слати листи тому, хто, можливо, її не вказував."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT user_id, email FROM app_user "
            " WHERE is_active AND email_verified AND email_alerts "
            "   AND EXISTS (SELECT 1 FROM watchlist w WHERE w.user_id = app_user.user_id)"
        ).fetchall()


# ═══════════════════════ канонічна модель товару (S30) ═══════════════════════
# ⚠ Детекція знижки лишається ПОСТОРІНКОВОЮ: закон говорить про мінімум за 30 днів
# У ЦЬОГО ПРОДАВЦЯ. «Модельний» мінімум по всіх крамницях статутною базою не є й
# бейджем стати не може. Модель — для ПОРІВНЯННЯ, детекція — для однієї сторінки.
def model_card(conn, product_id: int):
    """Модель + усі її сторінки в крамницях, від найдешевшої."""
    with conn.cursor(row_factory=dict_row) as cur:
        head = cur.execute(
            "SELECT p.product_id, p.match_key, p.title, c.name AS category, c.slug AS category_slug "
            "  FROM product p LEFT JOIN category c ON c.category_id = p.category_id "
            " WHERE p.product_id = %s", (product_id,)).fetchone()
        if head is None:
            return None
        head["offers"] = cur.execute(
            "WITH latest AS ("
            "  SELECT DISTINCT ON (ps.store_product_id) ps.store_product_id,"
            "         ps.price_now_kop, ps.seen_at, ps.in_stock"
            "    FROM price_snapshot ps"
            "   WHERE ps.store_product_id IN (SELECT store_product_id FROM store_product"
            "                                  WHERE match_key = %s)"
            "   ORDER BY ps.store_product_id, ps.seen_at DESC) "
            "SELECT sp.store_product_id, sp.title, sp.url, sp.image_url,"
            "       s.name AS store, l.price_now_kop AS current_kop, l.seen_at,"
            "       de.badge_state, de.old_declared_kop, de.reference_kop"
            "  FROM store_product sp"
            "  JOIN source s USING (source_id)"
            "  LEFT JOIN latest l ON l.store_product_id = sp.store_product_id"
            "  LEFT JOIN discount_event de ON de.store_product_id = sp.store_product_id"
            "                             AND de.ended_at IS NULL"
            " WHERE sp.match_key = %s"
            " ORDER BY l.price_now_kop NULLS LAST, s.name", (head["match_key"], head["match_key"])).fetchall()
    prices = [o["current_kop"] for o in head["offers"] if o["current_kop"] is not None]
    head["min_kop"] = min(prices) if prices else None
    head["max_kop"] = max(prices) if prices else None
    head["stores_n"] = len({o["store"] for o in head["offers"]})
    # Фото беремо з першої сторінки, де воно є: це ВКАЗІВНИК (hotlink), байти не наші.
    head["image_url"] = next((o["image_url"] for o in head["offers"] if o["image_url"]), None)
    return head


def model_of_store_product(conn, store_product_id: int):
    """product_id сторінки крамниці; None — коли модель не впізнана (немає match_key)."""
    row = conn.execute(
        "SELECT p.product_id FROM store_product sp "
        "  JOIN product p ON p.match_key = sp.match_key "
        " WHERE sp.store_product_id = %s", (store_product_id,)).fetchone()
    return row[0] if row and row[0] is not None else None


def refresh_models(conn) -> int:
    """Створити нові моделі й підтягнути канонічні назви. Ходить після інджесту.

    Тригера більше немає (0176): у PostgreSQL BEFORE-тригер НЕ БАЧИТЬ генерованих
    колонок — `NEW.match_key` там завжди NULL, і саме через це перший варіант звʼязав
    рівно нуль сторінок. Звʼязок тепер живе в самих даних (join за `match_key`), а ця
    функція лише тримає довідник моделей свіжим."""
    n = conn.execute(
        "INSERT INTO product (match_key, title, category_id) "
        "SELECT DISTINCT ON (match_key) match_key, title, category_id "
        "  FROM store_product WHERE match_key IS NOT NULL "
        " ORDER BY match_key, length(title), store_product_id "
        "ON CONFLICT (match_key) DO NOTHING").rowcount
    conn.execute(
        "UPDATE product p SET title = best.title "
        "  FROM (SELECT DISTINCT ON (match_key) match_key, title FROM store_product "
        "         WHERE match_key IS NOT NULL "
        "         ORDER BY match_key, length(title), store_product_id) best "
        " WHERE p.match_key = best.match_key AND p.title IS DISTINCT FROM best.title")
    return n


# ═══════════════════════ печатка доби: доказовість (S31) ═══════════════════════
def day_rows(conn, day: str):
    """Усі спостереження доби у КАНОНІЧНОМУ порядку.

    Порядок — частина публічного контракту: інший порядок дасть інший корінь, і чужий
    скрипт не відтворить наш результат. Беремо (seen_at, price_snapshot_id) — перше
    змістовне, друге гарантує однозначність при однаковій мітці часу."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT price_snapshot_id, store_product_id, price_now_kop, price_old_kop,"
            "       in_stock, seen_at "
            "  FROM price_snapshot "
            " WHERE seen_at >= %s::date AND seen_at < (%s::date + 1) "
            " ORDER BY seen_at, price_snapshot_id", (day, day)).fetchall()


def unsealed_days(conn):
    """Повні доби, які ще не запечатані. СЬОГОДНІШНЮ не чіпаємо: доба ще триває, і
    печатка на неповних даних була б хибною за побудовою."""
    return [r[0].isoformat() for r in conn.execute(
        "SELECT DISTINCT seen_at::date AS d FROM price_snapshot "
        " WHERE seen_at::date < current_date "
        "   AND seen_at::date NOT IN (SELECT day FROM day_seal) "
        " ORDER BY d").fetchall()]


def last_seal(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT * FROM day_seal ORDER BY day DESC LIMIT 1").fetchone()


def insert_seal(conn, day: str, rows_n: int, merkle_root: str,
                prev_chain: str | None, chain: str) -> None:
    conn.execute(
        "INSERT INTO day_seal (day, rows_n, merkle_root, prev_chain, chain) "
        "VALUES (%s,%s,%s,%s,%s)", (day, rows_n, merkle_root, prev_chain, chain))


def seals(conn, limit: int = 60):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT day, rows_n, merkle_root, prev_chain, chain, sealed_at "
            "  FROM day_seal ORDER BY day DESC LIMIT %s", (limit,)).fetchall()


def seal_of_day(conn, day: str):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT * FROM day_seal WHERE day = %s", (day,)).fetchone()


def snapshot_for_proof(conn, price_snapshot_id: int):
    """Один снапшот + доба, до якої він належить — щоб зібрати доказ."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT price_snapshot_id, store_product_id, price_now_kop, price_old_kop,"
            "       in_stock, seen_at, seen_at::date AS day "
            "  FROM price_snapshot WHERE price_snapshot_id = %s",
            (price_snapshot_id,)).fetchone()


# Скільки перевірених подій потрібно, щоб узагалі називати відсоток. 1000 — не
# статистична істина, а свідомо консервативний поріг: на 116 подіях різниця між 45% і
# 60% — це шум, а публікація такого числа коштувала б нам саме тієї репутації, заради
# якої продукт існує. 🧭 Величина під людським ревʼю (інваріант C).
MARKET_MIN_SAMPLE = 1000


def market_index(conn, days: int = 30):
    """Ринковий зріз: скільки заявлених знижок ми змогли ПЕРЕВІРИТИ і що побачили.

    ⚠ Головне тут — `sample_n` і `confident`. На 2026-07-28 перевірених подій було 116,
    з них 62 із завищеною старою ціною. «53% знижок накачані» на вибірці 116 — це рівно
    та накачана знижка, яку ми ловимо в крамниць, тож поки вибірка мала, число
    показуємо як СИРИЙ ЛІЧИЛЬНИК, без відсотка й без висновку.

    Поріг — параметр, а не істина: він під людським ревʼю (інваріант C)."""
    row = conn.execute(
        "SELECT count(*) FILTER (WHERE reference_kop IS NOT NULL)::int AS checked,"
        "       count(*) FILTER (WHERE badge_state = 'pumped')::int AS pumped,"
        "       count(*) FILTER (WHERE badge_state IN "
        "              ('verified','verified_provisional'))::int AS verified,"
        "       count(*)::int AS declared_total "
        "  FROM discount_event "
        " WHERE ended_at IS NULL AND computed_at > now() - make_interval(days => %s)",
        (days,)).fetchone()
    checked, pumped, verified, total = row
    return {
        "days": days,
        "declared_total": total,
        "sample_n": checked,
        "pumped": pumped,
        "verified": verified,
        "min_sample": MARKET_MIN_SAMPLE,
        # Висновок робимо, лише коли вибірка це дозволяє. Інакше віддаємо факти й
        # мовчимо — так само, як мовчимо про товар, у якого замало історії.
        "confident": checked >= MARKET_MIN_SAMPLE,
        "pumped_pct": (round(100 * pumped / checked) if checked >= MARKET_MIN_SAMPLE else None),
    }
