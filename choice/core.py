"""«Наш вибір» v1 (S9) — чисте ядро скора. Жодного I/O; гроші — цілі копійки.

score = w_price·price_score + w_honesty·honesty_score + pickup_bonus·[has_pickup]

- Кандидати — лише in_stock (фільтр, не вага): відсутній товар не купиш.
- price_score рахується від ЕФЕКТИВНОЇ ціни (з доставкою за правилом крамниці);
  нема правила → доставка 0 + прапорець no_delivery_data (UI мусить показати).
- honesty_score = 1 − pumped_share(source), Лаплас: (pumped+α)/(events+2α) —
  крамниця без жодної події отримує нейтральні 0.5, а не фальшиву одиницю.
- Формула ПУБЛІЧНА й пояснювана: pick() віддає складники кожного кандидата.
- Ваги приходять із таблиці choice_weights (Decimal) — тут НЕ хардкодяться.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Weights:
    w_price: Decimal
    w_honesty: Decimal
    pickup_bonus: Decimal
    laplace_alpha: Decimal


@dataclass(frozen=True)
class Offer:
    """Одна пропозиція-кандидат (рядок «Де купити») + довідникові атрибути її крамниці."""
    store: str
    price_now_kop: int
    in_stock: bool
    free_from_kop: int | None    # None + base=None → правила нема (no_delivery_data)
    base_delivery_kop: int | None
    pumped_events: int           # discount_event крамниці зі станом pumped (вікно 90 дн)
    total_events: int            # усі discount_event крамниці за те саме вікно
    has_pickup: bool


def effective_kop(o: Offer) -> tuple[int, bool]:
    """(ефективна ціна, no_delivery_data). Правило: безкоштовно від free_from_kop."""
    if o.base_delivery_kop is None:
        return o.price_now_kop, True
    if o.free_from_kop is not None and o.price_now_kop >= o.free_from_kop:
        return o.price_now_kop, False
    return o.price_now_kop + o.base_delivery_kop, False


def honesty_score(o: Offer, alpha: Decimal) -> Decimal:
    """1 − згладжена частка pumped. 0 подій → рівно 0.5 (нейтрально, не «свята»)."""
    pumped = Decimal(o.pumped_events)
    total = Decimal(o.total_events)
    share = (pumped + alpha) / (total + 2 * alpha)
    return Decimal(1) - share


def pick(offers: list[Offer], w: Weights) -> dict | None:
    """Обирає our_choice серед in_stock-кандидатів. Повертає dict зі складниками
    КОЖНОГО кандидата (пояснюваність — вимога брифа) або None:
    - нема жодного in_stock-кандидата;
    - кандидат один (нема з чим порівнювати — блок не показується, guardrail §7).
    """
    cands = [o for o in offers if o.in_stock and o.price_now_kop > 0]
    if len(cands) < 2:
        return None
    eff = {o.store: effective_kop(o) for o in cands}
    lo = min(e for e, _nd in eff.values())
    hi = max(e for e, _nd in eff.values())
    rows = []
    for o in cands:
        e, nodata = eff[o.store]
        # ВІДНОШЕННЯ до найдешевшої (lo/eff), НЕ спан-нормування: спан робить
        # копійчану різницю «повним спектром» і глушить чесність (впіймано
        # golden-тестом перекидання). Дорожча на 1% → 0.99; удвічі → 0.5 —
        # чесність (вага 0.25) перекидає лише СПРАВДІ близькі ціни.
        price_score = Decimal(lo) / Decimal(e)
        hon = honesty_score(o, w.laplace_alpha)
        bonus = w.pickup_bonus if o.has_pickup else Decimal(0)
        score = w.w_price * price_score + w.w_honesty * hon + bonus
        rows.append({
            "store": o.store, "effective_kop": e, "no_delivery_data": nodata,
            "delivery_kop": e - o.price_now_kop,
            # сирі лічильники перевірок — ФАКТ для UI-бейджа (юр-рішення 2026-07-24:
            # жодних «чесність N%» назовні — лише фактологічне «знижки збігаються з
            # історією цін» / «"старі" ціни часто вищі за реальні», і лише при
            # достатніх даних; пороги — на стороні клієнта від цих чисел)
            "discounts_checked": o.total_events,
            "discounts_passed": o.total_events - o.pumped_events,
            "components": {"price_score": float(round(price_score, 4)),
                           "honesty_score": float(round(hon, 4)),
                           "pickup_bonus": float(bonus)},
            "score": float(round(score, 4)),
        })
    # стабільний тай-брейк: рівний скор → дешевша ефективна, тоді алфавіт крамниці;
    # кандидати сортуються ТИМ САМИМ ключем — переможець завжди перший рядок
    key = lambda r: (r["score"], -r["effective_kop"], r["store"])
    best = max(rows, key=key)
    return {
        "our_choice": best["store"],
        "effective_kop": best["effective_kop"],
        "savings_kop": hi - best["effective_kop"],
        "candidates": sorted(rows, key=key, reverse=True),
    }
