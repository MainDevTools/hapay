"""Query-хелпери read-API (§9.1/§9.2). Лише читання (+watchlist). dict-рядки для JSON.

Клієнт сюди не має прямого доступу — тільки через api/main.py (§8.10.1).
Гроші повертаємо в копійках (int); формат у грн — на клієнті.
"""
from __future__ import annotations
from psycopg import errors
from psycopg.rows import dict_row

_SORTS = {
    "verified": "de.verified_pct DESC NULLS LAST, de.computed_at DESC",
    "discount": "de.declared_pct DESC NULLS LAST, de.computed_at DESC",
    "new":      "de.computed_at DESC",
}


def list_discounts(conn, category=None, badge=None, sort="verified", limit=50, offset=0, q=None,
                   price_min=None, price_max=None):
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
        SELECT de.discount_event_id, sp.store_product_id, sp.title, sp.url, sp.image_url,
               sp.variant_note, s.name AS store,
               de.current_kop, de.old_declared_kop, de.reference_kop,
               de.declared_pct, de.verified_pct, de.badge_state
        FROM discount_event de
        JOIN store_product sp USING (store_product_id)
        JOIN source s USING (source_id)
        JOIN category c ON c.category_id = sp.category_id
        WHERE {' AND '.join(where)}
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


def product_offers(conn, store_product_id: int):
    """«Де купити» (T15/§17.5): усі крамниці з ТИМ САМИМ товаром (однаковий mpn),
    остання відома ціна кожної, сортовано від найдешевшої. Включає сам товар.

    Товар без mpn → [] (немає ключа групування — блок у застосунку не показується).
    Ціна — з СИРОГО price_snapshot (останній вимір), не з discount_event: оффер
    крамниці існує й без активної знижки.
    """
    sql = """
        WITH grp AS (
            SELECT sp.store_product_id, sp.title, sp.url, s.name AS store
            FROM store_product sp
            JOIN source s USING (source_id)
            WHERE sp.mpn IS NOT NULL
              AND sp.mpn = (SELECT mpn FROM store_product WHERE store_product_id = %s)
        ),
        last_price AS (
            SELECT DISTINCT ON (ps.store_product_id)
                   ps.store_product_id, ps.price_now_kop, ps.in_stock,
                   (ps.seen_at AT TIME ZONE 'Europe/Kyiv')::date AS seen_day
            FROM price_snapshot ps
            JOIN grp USING (store_product_id)
            ORDER BY ps.store_product_id, ps.seen_at DESC
        )
        SELECT g.store_product_id, g.store, g.title, g.url,
               lp.price_now_kop AS current_kop, lp.in_stock, lp.seen_day
        FROM grp g
        JOIN last_price lp USING (store_product_id)
        ORDER BY lp.price_now_kop, g.store"""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (store_product_id,)).fetchall()


def categories(conn):
    """Лише категорії з активними знижками (+ лічильник) — для селектора §9.1."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT c.slug, c.name, count(*) AS n "
            "FROM category c "
            "JOIN store_product sp ON sp.category_id = c.category_id "
            "JOIN discount_event de ON de.store_product_id = sp.store_product_id "
            "WHERE de.ended_at IS NULL "
            "GROUP BY c.slug, c.name ORDER BY n DESC").fetchall()


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
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "INSERT INTO watchlist (user_id, kind, ref_id, query_text) VALUES (%s,%s,%s,%s) "
            "RETURNING watchlist_id, kind, ref_id, query_text",
            (user_id, kind, ref_id, query_text)).fetchone()


def list_watchlist_user(conn, user_id: int):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT watchlist_id, kind, ref_id, query_text, created_at FROM watchlist "
            "WHERE user_id = %s ORDER BY created_at DESC", (user_id,)).fetchall()
