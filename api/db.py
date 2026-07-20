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
}


def list_products(conn, category=None, sort="discount", limit=50, offset=0, q=None,
                  price_min=None, price_max=None, only_discounts=False):
    """УСІ товари (не лише знижкові), остання відома ціна кожного, MPN-дедуп як стрічка.

    Розворот у бік повного прайс-агрегатора: показуємо весь зібраний каталог, а знижка —
    бейдж на картці (has_discount), не єдиний критерій. `only_discounts=True` звужує до
    знижкових (сумісність зі старою стрічкою). Ціна — з останнього price_snapshot.
    """
    where = ["sp.last_seen_at > now() - interval '3 days'", "l.in_stock"]
    params: list = []
    if category:
        where.append("c.slug = %s"); params.append(category)
    if q:
        where.append("sp.title ILIKE %s"); params.append(f"%{q.strip()}%")
    if price_min is not None:
        where.append("l.current_kop >= %s"); params.append(price_min)
    if price_max is not None:
        where.append("l.current_kop <= %s"); params.append(price_max)
    if only_discounts:
        where.append("de.discount_event_id IS NOT NULL")
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
                   s.name AS store, sp.first_seen_at,
                   l.current_kop, l.old_declared_kop,
                   de.discount_event_id, de.declared_pct, de.verified_pct,
                   COALESCE(de.badge_state, 'none') AS badge_state,
                   COALESCE(sp.mpn, 'sp:' || sp.store_product_id) AS gkey
            FROM latest l
            JOIN store_product sp USING (store_product_id)
            JOIN source s USING (source_id)
            JOIN category c ON c.category_id = sp.category_id
            LEFT JOIN discount_event de
                   ON de.store_product_id = l.store_product_id AND de.ended_at IS NULL
            WHERE {' AND '.join(where)}
        ),
        best AS (   -- одна картка на групу (MPN): найдешевша, знижкова пріоритетно
            SELECT DISTINCT ON (gkey)
                   store_product_id, title, url, image_url, variant_note, mpn, store,
                   first_seen_at, current_kop, old_declared_kop, declared_pct, verified_pct,
                   badge_state, discount_event_id
            FROM ev ORDER BY gkey, (discount_event_id IS NOT NULL) DESC, current_kop
        )
        SELECT b.store_product_id, b.title, b.url, b.image_url, b.variant_note, b.store,
               b.current_kop, b.old_declared_kop, b.declared_pct, b.verified_pct, b.badge_state,
               (b.discount_event_id IS NOT NULL) AS has_discount,
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
            SELECT sp.store_product_id, sp.source_id, sp.title, sp.url, s.name AS store
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
            SELECT g.source_id, g.store_product_id, g.store, g.title, g.url,
                   lp.price_now_kop AS current_kop, lp.price_old_kop AS old_declared_kop,
                   lp.in_stock, lp.seen_day
            FROM grp g JOIN last_price lp USING (store_product_id)
        ),
        per_store AS (   -- одна найдешевша (та в наявності пріоритетно) пропозиція на крамницю
            SELECT DISTINCT ON (source_id) store_product_id, store, title, url,
                   current_kop, old_declared_kop, in_stock, seen_day
            FROM joined
            ORDER BY source_id, in_stock DESC, current_kop
        )
        SELECT store_product_id, store, title, url, current_kop, old_declared_kop, in_stock, seen_day
        FROM per_store ORDER BY current_kop, store"""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (store_product_id,)).fetchall()


def categories(conn):
    """Лише категорії з активними знижками (+ лічильник) — для селектора §9.1 та
    сітки-каталогу §17. Порожні (без знижок) НЕ повертаємо. Кожну збагачуємо розділом
    і іконкою (taxonomy.category_ui); сортуємо за розділом, тоді за к-стю (більше — вище)."""
    # image_url — фото товару-представника (найбільша знижка в категорії): плитка
    # каталогу з реальним фото, як в E-Katalog. Це ВКАЗІВНИК (hotlink), байти не зберігаємо (§7.4).
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT c.slug, c.name, count(*) AS n, "
            "       (array_agg(sp.image_url ORDER BY de.declared_pct DESC NULLS LAST) "
            "        FILTER (WHERE sp.image_url IS NOT NULL))[1] AS image_url "
            "FROM category c "
            "JOIN store_product sp ON sp.category_id = c.category_id "
            "JOIN discount_event de ON de.store_product_id = sp.store_product_id "
            "WHERE de.ended_at IS NULL "
            "GROUP BY c.slug, c.name").fetchall()
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
