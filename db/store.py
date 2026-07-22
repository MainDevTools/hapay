"""Персист RawItem (S2) → store_product + price_snapshot (§6.3).

Довід, що схема приймає вихід екстрактора: upsert товару за UNIQUE(source_id, external_ref),
потім append-only insert снапшота ціни. Гроші — цілі копійки (A1).
detect_pass/бейджі — поза скоупом (S3).
"""
from __future__ import annotations
from adapters.base import RawItem
from matching import extract_mpn, pick_gtin
from taxonomy import categorize, refine_category


def load_categories(conn) -> dict[str, int]:
    """slug → category_id (включно з 'uncategorized' і сідами 0002)."""
    return {slug: cid for slug, cid in
            conn.execute("SELECT slug, category_id FROM category").fetchall()}


def upsert_source(conn, name: str, base_url: str, *, adapter_kind: str = "ssr",
                  platform: str | None = None, discount_url: str | None = None,
                  fetch_tier: str | None = None) -> int:
    row = conn.execute(
        """INSERT INTO source (name, base_url, discount_url, platform, adapter_kind, fetch_tier)
           VALUES (%s,%s,%s,%s,%s,%s)
           ON CONFLICT (base_url) DO UPDATE SET name = EXCLUDED.name
           RETURNING source_id""",
        (name, base_url, discount_url, platform, adapter_kind, fetch_tier),
    ).fetchone()
    return row[0]


def persist_items(conn, source_id: int, items: list[RawItem], categories: dict[str, int], *,
                  source_method: str = "css", scan_run_id: int | None = None,
                  category_slug: str | None = None) -> int:
    """Upsert товарів + insert снапшотів. Повертає к-сть снапшотів.

    `category_slug` (з лістинга, який зібрали) має пріоритет — надійніше за вгадування з
    URL (§2.6). Якщо не задано (зоо-збір) — категорія виводиться з URL (categorize).
    Далі `refine_category` уточнює за назвою (кабель/навушники з широкого департаменту
    «Смартфони та зв'язок» → aksesuary/audio, а не smartfony).
    """
    fallback = categories.get("uncategorized") or categories.get("inshe")
    n = 0
    for it in items:
        base_slug = category_slug or categorize(it.url)
        final_slug = refine_category(base_slug, it.title)
        category_id = categories.get(final_slug) or categories.get(base_slug) or fallback
        sp = conn.execute(
            """INSERT INTO store_product
                 (source_id, external_ref, url, title, image_url, category_id,
                  variant_note, needs_variant_resolution, mpn, gtin, promo_until, last_seen_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (source_id, external_ref) DO UPDATE
                 SET url = EXCLUDED.url, title = EXCLUDED.title,
                     image_url = EXCLUDED.image_url, variant_note = EXCLUDED.variant_note,
                     category_id = EXCLUDED.category_id, mpn = EXCLUDED.mpn,
                     gtin = EXCLUDED.gtin,
                     promo_until = EXCLUDED.promo_until, last_seen_at = now()
               RETURNING store_product_id""",
            (source_id, it.external_ref, it.url, it.title, it.image_url, category_id,
             it.variant_note, False, extract_mpn(it.title), pick_gtin(it.gtins), it.promo_until),
        ).fetchone()
        conn.execute(
            """INSERT INTO price_snapshot
                 (store_product_id, price_now_kop, price_old_kop, in_stock, source_method,
                  seen_at, scan_run_id, is_backfill)
               VALUES (%s,%s,%s,%s,%s, now(), %s, FALSE)""",
            (sp[0], it.price_now_kop, it.price_old_kop, it.in_stock, source_method, scan_run_id),
        )
        n += 1
    return n
