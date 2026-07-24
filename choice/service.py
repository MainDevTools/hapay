"""«Наш вибір» v1 (S9) — збирання даних для ядра: офери групи + довідники + чесність.

Читає ЛИШЕ наявні структури (product_offers-логіка повторно не дублюється — беремо
готовий список оферів як вхід) + delivery_rule/store_network/choice_weights +
pumped-частку з ВЛАСНИХ discount_event (юр-guardrail: жодних чужих рейтингів).
"""
from __future__ import annotations

from decimal import Decimal

from choice.core import Offer, Weights, pick

_HONESTY_WINDOW_DAYS = 90


def load_weights(conn) -> Weights:
    row = conn.execute(
        "SELECT w_price, w_honesty, pickup_bonus, laplace_alpha FROM choice_weights "
        "WHERE valid_from <= now() AND (valid_to IS NULL OR valid_to > now()) "
        "ORDER BY valid_from DESC LIMIT 1").fetchone()
    if row is None:                       # міграція 0159 сіє дефолт; це лише страховка
        return Weights(Decimal("0.70"), Decimal("0.25"), Decimal("0.05"), Decimal(1))
    return Weights(*(Decimal(x) for x in row))


def _store_facts(conn, stores: list[str]) -> dict[str, dict]:
    """Довідники + чесність по крамницях одним заходом. Ключ — source.name."""
    rows = conn.execute(
        """SELECT s.name,
                  dr.free_from_kop, dr.base_delivery_kop,
                  COALESCE(sn.has_pickup, false) AS has_pickup,
                  COALESCE(ev.pumped, 0) AS pumped, COALESCE(ev.total, 0) AS total
           FROM source s
           LEFT JOIN delivery_rule dr USING (source_id)
           LEFT JOIN store_network sn USING (source_id)
           LEFT JOIN (
               SELECT sp.source_id,
                      count(*) FILTER (WHERE de.badge_state = 'pumped') AS pumped,
                      count(*) AS total
               FROM discount_event de
               JOIN store_product sp USING (store_product_id)
               WHERE de.computed_at > now() - make_interval(days => %s)
               GROUP BY sp.source_id
           ) ev USING (source_id)
           WHERE s.name = ANY(%s)""",
        (_HONESTY_WINDOW_DAYS, stores)).fetchall()
    return {r[0]: {"free_from_kop": r[1], "base_delivery_kop": r[2],
                   "has_pickup": r[3], "pumped": r[4], "total": r[5]} for r in rows}


def our_choice(conn, offers: list[dict]) -> dict | None:
    """offers — вихід qdb.product_offers (dict-рядки: store, current_kop, in_stock…).
    Повертає pick()-результат зі складниками або None (нема ≥2 кандидатів)."""
    stores = sorted({o["store"] for o in offers})
    if len(stores) < 2:
        return None
    facts = _store_facts(conn, stores)
    cands = []
    for o in offers:
        f = facts.get(o["store"], {})
        cands.append(Offer(
            store=o["store"], price_now_kop=int(o["current_kop"] or 0),
            in_stock=bool(o["in_stock"]),
            free_from_kop=f.get("free_from_kop"),
            base_delivery_kop=f.get("base_delivery_kop"),
            pumped_events=int(f.get("pumped", 0)), total_events=int(f.get("total", 0)),
            has_pickup=bool(f.get("has_pickup", False))))
    w = load_weights(conn)
    result = pick(cands, w)
    if result is not None:
        # ваги — у відповідь: «Як ми рахуємо?» в UI показує ЖИВІ числа з
        # choice_weights, а не захардкоджений текст, що протух би при зміні політики
        result["weights"] = {"w_price": float(w.w_price), "w_honesty": float(w.w_honesty),
                             "pickup_bonus": float(w.pickup_bonus)}
    return result
