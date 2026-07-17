"""Query-хелпери read-API (§9.1/§9.2). Лише читання (+watchlist). dict-рядки для JSON.

Клієнт сюди не має прямого доступу — тільки через api/main.py (§8.10.1).
Гроші повертаємо в копійках (int); формат у грн — на клієнті.
"""
from __future__ import annotations
from psycopg.rows import dict_row

_SORTS = {
    "verified": "de.verified_pct DESC NULLS LAST, de.computed_at DESC",
    "discount": "de.declared_pct DESC NULLS LAST, de.computed_at DESC",
    "new":      "de.computed_at DESC",
}


def list_discounts(conn, category=None, badge=None, sort="verified", limit=50, offset=0, q=None):
    where = ["de.ended_at IS NULL"]
    params: list = []
    if category:
        where.append("c.slug = %s"); params.append(category)
    if badge:
        where.append("de.badge_state = %s"); params.append(badge)
    if q:                                   # пошук за назвою (ILIKE — прощає часткові; §9.1)
        where.append("sp.title ILIKE %s"); params.append(f"%{q.strip()}%")
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
