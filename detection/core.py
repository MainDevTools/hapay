"""Ядро детекції знижки (§5) — ЧИСТА логіка, без БД і без системного годинника.

`now` і історія подаються ззовні (інжектований час — §8.8), тож детермінована й
тестується синтетичними історіями. Гроші — цілі копійки; відсотки — Decimal
ROUND_HALF_UP (§5.1), не float/банкірське округлення.

Джерело бази — СИРІ точки історії (аналог price_snapshot), ніколи агрегат (§5.2, юр).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP


def pct(delta_kop: int, base_kop: int) -> int:
    """Відсоток із ROUND_HALF_UP (§5.1): 4,5%→5%. base>0 (гарантує викликач)."""
    return int((Decimal(100) * Decimal(delta_kop) / Decimal(base_kop)).quantize(0, ROUND_HALF_UP))


@dataclass(frozen=True)
class Point:
    day: date            # київська цивільна доба заміру (§5.2)
    price_kop: int
    in_stock: bool = True


@dataclass(frozen=True)
class Config:
    window_days: int = 30
    min_verified_pct: int = 5
    min_reference_points: int = 10
    provisional_min_points: int = 4
    declared_ratio_max: float = 5.0
    min_declared_pct: int = 1        # нижче — не знижка, а шум (рішення власника 2026-07-21)
    campaign_gap_days: int = 7
    announce_confirm_points: int = 2
    exclude_oos_from_window: bool = True


@dataclass(frozen=True)
class Badge:
    badge_state: str            # verified|verified_provisional|pumped|insufficient_history|declared
    current_kop: int
    announce_date: date | None = None
    reference_kop: int | None = None
    verified_pct: int | None = None
    declared_pct: int | None = None
    n_points: int = 0


# ─────────────────────────── Стадія A (§5.1) ───────────────────────────

def declared_pct(current_kop: int, old_kop: int | None, cfg: Config) -> int | None:
    """Заявлена знижка + sanity: РРЦ/парс-помилку (old/current > ratio_max або old<current) не показуємо."""
    if old_kop is None or current_kop <= 0 or old_kop <= current_kop:
        return None
    if old_kop / current_kop > cfg.declared_ratio_max:      # напр. −80%+ на кормі = майже завжди артефакт
        return None
    # Нижній поріг: −0,2% це не знижка. Порівнюємо СПРАВЖНІЙ відсоток, ДО округлення —
    # інакше 0,75% округлилось би до 1% і пролізло б крізь поріг «від 1%». На проді таких
    # подій було 27 (7 малювали «−0%», 20 — «−1%»); найменша — 0,011%.
    raw = Decimal(100) * Decimal(old_kop - current_kop) / Decimal(old_kop)
    if raw < Decimal(cfg.min_declared_pct):
        return None
    return pct(old_kop - current_kop, old_kop)


# ─────────────────────────── Стадія B (§5.2) ───────────────────────────

def _valid_window(points: list[Point], announce_day: date, cfg: Config) -> list[Point]:
    """Точки у [announce−window, announce): in_stock (якщо exclude_oos) і ціна>0 (§5.2/§5.5)."""
    lo = announce_day - timedelta(days=cfg.window_days)
    return [p for p in points
            if lo <= p.day < announce_day
            and p.price_kop > 0
            and (p.in_stock or not cfg.exclude_oos_from_window)]


def _is_discounted(points: list[Point], day: date, cur_kop: int, cfg: Config) -> bool:
    """День day знижений відносно попередньої 30-денної бази (§5.2): ціна < prior_min×(1−поріг),
    і база рахована на ≥ min_reference_points точок (інакше не інферуємо — крайовий випадок 1)."""
    win = _valid_window(points, day, cfg)
    if len(win) < cfg.min_reference_points:
        return False
    prior_min = min(p.price_kop for p in win)
    thr = Decimal(1) - Decimal(cfg.min_verified_pct) / 100
    return Decimal(cur_kop) < Decimal(prior_min) * thr


def infer_announce_day(points: list[Point], cfg: Config) -> date | None:
    """Початок ПОТОЧНОЇ кампанії (§5.2 варіант б / §5.5): перший день найсвіжішого
    знижено-прогону, що триває до останнього дня (внутрішні розриви < campaign_gap_days —
    та сама кампанія). None, якщо останній день не знижений."""
    by_day: dict[date, int] = {}
    for p in points:                                       # представник доби — мінімальна валідна ціна
        if p.price_kop > 0 and (p.in_stock or not cfg.exclude_oos_from_window):
            by_day[p.day] = min(by_day.get(p.day, p.price_kop), p.price_kop)
    days = sorted(by_day)
    if not days:
        return None
    disc = {d: _is_discounted(points, d, by_day[d], cfg) for d in days}
    if not disc[days[-1]]:
        return None                                        # зараз не знижений → нема активної події
    start = days[-1]
    for d in reversed(days):
        if disc[d]:
            start = d
        elif (start - d).days >= cfg.campaign_gap_days:    # розрив ≥ порога → попередня кампанія
            break
    return start


def compute_badge(points: list[Point], now_day: date, current_kop: int, cfg: Config,
                  old_kop: int | None = None, announce_day: date | None = None) -> Badge:
    """Повний бейдж §5.3. announce_day: якщо задано (прапор акції / заморожена подія) — беремо його;
    інакше інферуємо; інакше (нова/незіставна) — now_day (свіжо побачена знижка)."""
    dp = declared_pct(current_kop, old_kop, cfg)
    if announce_day is None:
        announce_day = infer_announce_day(points, cfg) or now_day

    win = _valid_window(points, announce_day, cfg)
    n = len(win)

    # мало історії → нейтральний declared (є стара ціна) або insufficient (§5.3 вузол G)
    if n < cfg.provisional_min_points:
        state = "declared" if dp is not None else "insufficient_history"
        return Badge(state, current_kop, announce_day, None, None, dp, n)

    reference_kop = min(p.price_kop for p in win)
    verified = pct(reference_kop - current_kop, reference_kop)   # може бути ≤0 (§5.2)

    if verified < cfg.min_verified_pct:
        state = "pumped"                                   # заявлено знижку, реально не нижче мінімуму
    else:
        earliest = min(p.day for p in win)
        full_30d = (announce_day - earliest).days >= cfg.window_days - 1
        state = "verified" if (n >= cfg.min_reference_points and full_30d) else "verified_provisional"

    return Badge(state, current_kop, announce_day, reference_kop, verified, dp, n)
