"""Query-хелпери read-API (§9.1/§9.2). Лише читання (+watchlist). dict-рядки для JSON.

Клієнт сюди не має прямого доступу — тільки через api/main.py (§8.10.1).
Гроші повертаємо в копійках (int); формат у грн — на клієнті.
"""
from __future__ import annotations
from psycopg import errors
from psycopg.rows import dict_row
from taxonomy import category_ui, SECTION_ORDER

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


def list_discounts(conn, category=None, badge=None, sort="verified", limit=50, offset=0, q=None,
                   price_min=None, price_max=None):
    """Стрічка знижок — АГРЕГАТОРНА (T15/§17): одна картка на ТОВАР, не на крамницю.

    Товари з однаковим mpn колапсуються в одну картку, яку представляє НАЙДЕШЕВША
    пропозиція (клієнт показує «від X ₴· в N крамницях», а не назву однієї крамниці —
    інакше «чому Foxtrot, а не Allo?»). Товари без mpn — кожен сам собі (gkey='sp:<id>').
    `offers_n` = к-сть РІЗНИХ крамниць у групі; «Де купити» (product_offers) деталізує.
    """
    where = ["de.ended_at IS NULL"]
    params: list = []
    if category:
        where.append("c.slug = %s"); params.append(category)
    if badge:
        where.append("de.badge_state = %s"); params.append(badge)
    if q:                                   # пошук за назвою (ILIKE — прощає часткові; §9.1)
        where.append("sp.title ILIKE %s"); params.append(f"%{q.strip()}%")
    if price_min is not None:               # ціна — копійки (інв. A); фільтр за поточною ціною
        where.append("de.current_kop >= %s"); params.append(price_min)
    if price_max is not None:
        where.append("de.current_kop <= %s"); params.append(price_max)
    order = _SORTS.get(sort, _SORTS["verified"])
    sql = f"""
        WITH ev AS (
            SELECT de.discount_event_id, sp.store_product_id, sp.title, sp.url, sp.image_url,
                   sp.variant_note, sp.mpn, s.name AS store,
                   de.current_kop, de.old_declared_kop, de.reference_kop,
                   de.declared_pct, de.verified_pct, de.badge_state, de.computed_at,
                   COALESCE(sp.mpn, 'sp:' || sp.store_product_id) AS gkey
            FROM discount_event de
            JOIN store_product sp USING (store_product_id)
            JOIN source s USING (source_id)
            JOIN category c ON c.category_id = sp.category_id
            WHERE {' AND '.join(where)}
        ),
        best AS (   -- одна картка на групу: представляє найдешевша (в наявності пріоритетно)
            SELECT DISTINCT ON (gkey)
                   discount_event_id, store_product_id, title, url, image_url, variant_note,
                   mpn, store, current_kop, old_declared_kop, reference_kop,
                   declared_pct, verified_pct, badge_state, computed_at
            FROM ev
            ORDER BY gkey, current_kop, badge_state
        )
        SELECT b.discount_event_id, b.store_product_id, b.title, b.url, b.image_url,
               b.variant_note, b.store, b.current_kop, b.old_declared_kop, b.reference_kop,
               b.declared_pct, b.verified_pct, b.badge_state,
               {_PROMO_COL}
               CASE WHEN b.mpn IS NULL THEN 1
                    ELSE (SELECT count(DISTINCT sp2.source_id)
                          FROM store_product sp2 WHERE sp2.mpn = b.mpn)
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


# сортування для «усіх товарів» (не лише знижок) — колонки з CTE best нижче
# кваліфікуємо b.* — бо JOIN store_product sp0 (для promo_until) теж має first_seen_at
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
                  price_min=None, price_max=None, only_discounts=False):
    """УСІ товари (не лише знижкові), остання відома ціна кожного, MPN-дедуп як стрічка.

    Розворот у бік повного прайс-агрегатора: показуємо весь зібраний каталог, а знижка —
    бейдж на картці (has_discount), не єдиний критерій. `only_discounts=True` звужує до
    знижкових (сумісність зі старою стрічкою). Ціна — з останнього price_snapshot.

    `cheaper_kop`/`cheaper_store` — та сама модель (mpn) ДЕШЕВШЕ в іншій крамниці.
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

    # звужувальні — лише для ВИБОРУ картки, не для пошуку дешевшої пропозиції
    narrow: list[str] = []
    if q:
        narrow.append("title ILIKE %s"); params.append(f"%{q.strip()}%")
    if price_min is not None:
        narrow.append("current_kop >= %s"); params.append(price_min)
    if price_max is not None:
        narrow.append("current_kop <= %s"); params.append(price_max)
    if only_discounts:
        narrow.append("discount_event_id IS NOT NULL")
    narrow_sql = ("WHERE " + " AND ".join(narrow)) if narrow else ""

    order = _PSORTS.get(sort, _PSORTS["discount"])
    sql = f"""
        WITH latest AS (   -- остання ціна кожного товару (index-scan по ix_ps_prod_window)
            SELECT DISTINCT ON (ps.store_product_id)
                   ps.store_product_id, ps.price_now_kop AS current_kop,
                   ps.price_old_kop AS old_declared_kop, ps.in_stock
            FROM price_snapshot ps
            ORDER BY ps.store_product_id, ps.seen_at DESC
        ),
        ev AS (
            SELECT l.store_product_id, sp.title, sp.url, sp.image_url, sp.variant_note, sp.mpn,
                   s.name AS store, sp.source_id, sp.first_seen_at,
                   l.current_kop, l.old_declared_kop,
                   de.discount_event_id, de.declared_pct, de.verified_pct,
                   COALESCE(de.badge_state, 'none') AS badge_state,
                   COALESCE(sp.mpn, 'sp:' || sp.store_product_id) AS gkey,
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
        alt AS (   -- кандидати «дешевше деінде»: уся група, БЕЗ уцінених/відновлених
            SELECT gkey,
                   array_agg(current_kop ORDER BY current_kop) AS kops,
                   array_agg(source_id   ORDER BY current_kop) AS srcs,
                   array_agg(store       ORDER BY current_kop) AS stores,
                   array_agg(shown_pct   ORDER BY current_kop) AS pcts
            FROM ev WHERE NOT used GROUP BY gkey
        ),
        best AS (   -- одна картка на групу (MPN): найдешевша, знижкова пріоритетно
            SELECT DISTINCT ON (gkey)
                   gkey, store_product_id, title, url, image_url, variant_note, mpn, store,
                   source_id, first_seen_at, current_kop, old_declared_kop, declared_pct,
                   verified_pct, badge_state, discount_event_id, shown_pct
            FROM ev {narrow_sql}
            -- `used` ПЕРШИМ: уцінене/відновлене не може представляти групу, поки в ній
            -- є чиста пропозиція. Інакше картка бере в уціненого і назву, і фото, і ціну:
            -- на проді «УЦІНКА Телевізор LG 50UA75006LA — від 16 999 ₴» очолювала групу,
            -- де ВІСІМ крамниць продають новий (заміряно 2026-07-21: таких груп 10).
            -- Якщо чистих у групі нема — уцінене лишається представником, товар реальний.
            ORDER BY gkey, used, (discount_event_id IS NOT NULL) DESC, current_kop
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
               CASE WHEN b.mpn IS NULL THEN 1
                    ELSE (SELECT count(DISTINCT sp2.source_id)
                          FROM store_product sp2 WHERE sp2.mpn = b.mpn)
               END AS offers_n
        FROM best b
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
        ORDER BY {order}
        LIMIT %s OFFSET %s"""
    params += [limit, offset]
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def product_offers(conn, store_product_id: int):
    """«Де купити» (T15/§17.5): ПО ОДНІЙ (найдешевшій) пропозиції на КРАМНИЦЮ з тим
    самим товаром (однаковий mpn), сортовано від найдешевшої. Включає сам товар.

    Дедуп по крамниці (не по товару): родовий артикул (OPPO CPH2801, Motorola PBA…)
    спільний для кольорових варіантів → без дедупу «Де купити» двічі писало б ту саму
    крамницю. Товар без mpn → [] (нема ключа групування). Ціна — з СИРОГО
    price_snapshot (оффер крамниці існує й без активної знижки).
    """
    sql = """
        WITH grp AS (
            SELECT sp.store_product_id, sp.source_id, sp.title, sp.url, s.name AS store,
                   (sp.title ~* %s) AS is_used
            FROM store_product sp
            JOIN source s USING (source_id)
            WHERE sp.mpn IS NOT NULL
              AND sp.mpn = (SELECT mpn FROM store_product WHERE store_product_id = %s)
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
            SELECT mpn, count(DISTINCT source_id) AS stores
            FROM store_product WHERE mpn IS NOT NULL GROUP BY mpn
        )
        SELECT cnt.slug, cnt.name, cnt.n, pic.image_url
        FROM cnt
        LEFT JOIN LATERAL (
            SELECT sp.image_url
            FROM store_product sp
            JOIN source s USING (source_id)
            JOIN discount_event de ON de.store_product_id = sp.store_product_id
                                  AND de.ended_at IS NULL
            LEFT JOIN grp g ON g.mpn = sp.mpn
            WHERE sp.category_id = cnt.category_id
              AND sp.image_url IS NOT NULL
              AND sp.title !~* %s
            ORDER BY CASE s.name {order_rank} ELSE 9 END,
                     COALESCE(g.stores, 1) DESC,
                     sp.store_product_id
            LIMIT 1
        ) pic ON TRUE"""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, (_TILE_SKIP_RE,)).fetchall()
    for r in rows:
        r["section"], r["icon"] = category_ui(r["slug"])
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
            "SELECT user_id, email, password_hash, role FROM app_user "
            "WHERE lower(email) = lower(%s)", (email,)).fetchone()


def touch_login(conn, user_id: int):
    conn.execute("UPDATE app_user SET last_login_at = now() WHERE user_id = %s", (user_id,))


def get_user(conn, user_id: int):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT user_id, email, role, created_at FROM app_user WHERE user_id = %s",
            (user_id,)).fetchone()


# watchlist на app-юзера (окремо від Telegram-версії вище)
def add_watchlist_user(conn, user_id: int, kind: str, ref_id: int | None, query_text: str | None):
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
        price = None
        if kind == "store_product" and ref_id is not None:
            row = cur.execute(
                "SELECT price_now_kop FROM price_snapshot WHERE store_product_id = %s "
                "ORDER BY seen_at DESC LIMIT 1", (ref_id,)).fetchone()
            price = row["price_now_kop"] if row else None
        return cur.execute(
            "INSERT INTO watchlist (user_id, kind, ref_id, query_text, price_at_add_kop) "
            "VALUES (%s,%s,%s,%s,%s) "
            "RETURNING watchlist_id, kind, ref_id, query_text, price_at_add_kop",
            (user_id, kind, ref_id, query_text, price)).fetchone()


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
        UPDATE watchlist w SET last_notified_kop = l.price_now_kop
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
               w.price_at_add_kop, sp.title, sp.url, sp.image_url,
               s.name AS store, l.price_now_kop AS current_kop,
               (l.price_now_kop - w.price_at_add_kop) AS delta_kop,
               CASE WHEN sp.mpn IS NULL THEN 1
                    ELSE (SELECT count(DISTINCT sp2.source_id)
                          FROM store_product sp2 WHERE sp2.mpn = sp.mpn)
               END AS offers_n
        FROM watchlist w
        LEFT JOIN store_product sp ON w.kind = 'store_product' AND sp.store_product_id = w.ref_id
        LEFT JOIN source s USING (source_id)
        LEFT JOIN latest l ON l.store_product_id = w.ref_id
        WHERE w.user_id = %s
        ORDER BY w.created_at DESC"""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (user_id, user_id)).fetchall()
