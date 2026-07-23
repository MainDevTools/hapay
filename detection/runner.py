"""detect_pass — обчислення бейджів поверх price_snapshot і upsert discount_event (§8.4).

Обов'язковий крок після кожного scan_run. Читає СИРИЙ price_snapshot (юр, §5.2),
київська доба через IANA-tz у SQL (`AT TIME ZONE 'Europe/Kyiv'`). Подію відкриваємо
лише для РЕАЛЬНОЇ знижки (заявлена або інферована) — інакше пласка ціна → хибний pumped.
announce відкритої події заморожено (§8.4 — проти дублів/сиріт).
"""
from __future__ import annotations
from datetime import date
from detection.core import Config, Point, compute_badge, declared_pct, infer_announce_day

# ПОРЯДОК = порядок полів у detection.core.Config (конструюємо позиційно, Config(*row)).
# Додаєш колонку — став її і тут, і в Config на ТУ САМУ позицію.
_CFG_COLS = ("window_days", "min_verified_pct", "min_reference_points", "provisional_min_points",
             "declared_ratio_max", "min_declared_pct", "campaign_gap_days", "announce_confirm_points",
             "exclude_oos_from_window")


def load_config(conn) -> Config:
    row = conn.execute(
        f"SELECT {','.join(_CFG_COLS)} FROM detection_config "
        "WHERE valid_from <= now() AND (valid_to IS NULL OR valid_to > now()) "
        "ORDER BY valid_from DESC LIMIT 1").fetchone()
    return Config(*row) if row else Config()


def _history(conn, store_product_id: int) -> list[Point]:
    rows = conn.execute(
        "SELECT (seen_at AT TIME ZONE 'Europe/Kyiv')::date, price_now_kop, in_stock "
        "FROM price_snapshot WHERE store_product_id = %s ORDER BY seen_at",
        (store_product_id,)).fetchall()
    return [Point(d, int(p), bool(s)) for d, p, s in rows]


def detect_pass(conn, now_day: date | None = None) -> int | None:
    """Прохід по всіх товарах зі снапшотами. Повертає к-сть upsert-нутих discount_event,
    або None — прохід ПРОПУЩЕНО, бо конкурентний detect_pass уже біжить.

    Серіалізація (2026-07-23): прохід викликається після КОЖНОГО page-інгесту; коли
    колектор надолужує чергу після простою, паралельні проходи билися за лок
    discount_event і падали LockNotAvailable (lock timeout) → 500 на ingest → здорова
    задача йшла у хибний fail-бекоф. try-лок на транзакцію: другий одночасний прохід
    не чекає (черга запитів не пухне), а пропускає — свіжі снапшоти добере наступний
    інгест (колектор шле сторінки щохвилини). Формулу/пороги НЕ чіпає — лише черговість.
    """
    got = conn.execute(
        "SELECT pg_try_advisory_xact_lock(hashtext('detect_pass'))").fetchone()[0]
    if not got:
        return None
    cfg = load_config(conn)
    spids = [r[0] for r in conn.execute(
        "SELECT DISTINCT store_product_id FROM price_snapshot").fetchall()]
    n = 0
    for spid in spids:
        pts = _history(conn, spid)
        if not pts:
            continue
        latest = conn.execute(
            "SELECT price_now_kop, price_old_kop, (seen_at AT TIME ZONE 'Europe/Kyiv')::date "
            "FROM price_snapshot WHERE store_product_id = %s ORDER BY seen_at DESC LIMIT 1",
            (spid,)).fetchone()
        current, old, latest_day = int(latest[0]), (int(latest[1]) if latest[1] is not None else None), latest[2]
        nd = now_day or latest_day

        frozen = conn.execute(
            "SELECT announce_date FROM discount_event "
            "WHERE store_product_id = %s AND ended_at IS NULL "
            "ORDER BY announce_date DESC LIMIT 1", (spid,)).fetchone()
        frozen_day = frozen[0] if frozen else None

        dp = declared_pct(current, old, cfg)
        inferred = infer_announce_day(pts, cfg)
        if dp is None and inferred is None and frozen_day is None:
            continue                          # не знижка — події не заводимо (уникаємо хибного pumped)

        announce = frozen_day or inferred or nd
        badge = compute_badge(pts, nd, current, cfg, old_kop=old, announce_day=announce)

        conn.execute(
            """INSERT INTO discount_event
                 (store_product_id, announce_date, current_kop, old_declared_kop,
                  declared_pct, reference_kop, verified_pct, badge_state)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (store_product_id, announce_date) DO UPDATE SET
                 current_kop = EXCLUDED.current_kop, old_declared_kop = EXCLUDED.old_declared_kop,
                 declared_pct = EXCLUDED.declared_pct, reference_kop = EXCLUDED.reference_kop,
                 verified_pct = EXCLUDED.verified_pct, badge_state = EXCLUDED.badge_state,
                 computed_at = now()""",
            (spid, badge.announce_date, current, old, badge.declared_pct,
             badge.reference_kop, badge.verified_pct, badge.badge_state))
        n += 1
    return n


def close_absent(conn, grace_hours: int = 26) -> int:
    """Закрити (`ended_at`) відкриті події товарів, які зникли з discovery (§8.4/§5.5):
    немає жодного снапшота за останні grace_hours (за замовч. трохи більше доби — товар
    відсутній у ≥2 денних сканах). Проксі discovery-відсутності для discovery-only колектора."""
    cur = conn.execute(
        """UPDATE discount_event de SET ended_at = now()
           WHERE de.ended_at IS NULL
             AND NOT EXISTS (
               SELECT 1 FROM price_snapshot ps
               WHERE ps.store_product_id = de.store_product_id
                 AND ps.seen_at > now() - make_interval(hours => %s))""",
        (grace_hours,))
    return cur.rowcount
