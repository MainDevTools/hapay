"""Golden-тести ядра детекції (§5) на синтетичних історіях. Час інжектований (§8.8).

Запуск:  python tests/test_detection.py   (або pytest). Без залежностей/БД.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detection.core import Config, Point, compute_badge, declared_pct, pct  # noqa: E402

CFG = Config()
D0 = date(2026, 6, 1)


def days(prices, in_stock=True, start=D0):
    return [Point(start + timedelta(days=i), p, in_stock) for i, p in enumerate(prices)]


# ── §5.1 pct + Стадія A ──

def test_pct_round_half_up():
    assert pct(45, 1000) == 5        # 4,5% → 5 (ROUND_HALF_UP; банкірське дало б 4)
    assert pct(-5000, 10000) == -50


def test_declared_pct_and_sanity():
    assert declared_pct(15000, 20000, CFG) == 25
    assert declared_pct(9000, 80000, CFG) is None     # 80000/9000≈8.9 > ratio_max → артефакт
    assert declared_pct(10000, 9000, CFG) is None     # old<current
    assert declared_pct(10000, None, CFG) is None


def test_declared_pct_min_threshold():
    """Нижній поріг (рішення власника: від 1%) — рахується ДО округлення.

    Це головне тут: 0,75% округлюється до 1%, і поріг на ОКРУГЛЕНОМУ значенні
    пропустив би такий випадок. На проді саме такі складали 20 із 27 підпорогових
    подій — вони виглядали як чесна «−1%».
    """
    assert declared_pct(8999900, 9019900, CFG) is None    # 0,22% — реальний випадок із проду
    assert declared_pct(99250, 100000, CFG) is None       # 0,75% → округлилось би до 1%
    assert declared_pct(99000, 100000, CFG) == 1          # рівно 1% — на порозі, лишається
    assert declared_pct(98500, 100000, CFG) == 2          # 1,5% → ROUND_HALF_UP → 2

    # поріг конфігурований (detection_config, міграція 0012): 0 = старе «будь-яке зниження»
    assert declared_pct(99250, 100000, Config(min_declared_pct=0)) == 1
    # і навпаки: підняття порога відсікає більше
    assert declared_pct(98500, 100000, Config(min_declared_pct=5)) is None


# ── §5.3 стани ──

def test_verified_full():
    """30 днів по 100 грн, потім поточна 80 → зелений повний, −20%."""
    b = compute_badge(days([10000] * 30), D0 + timedelta(days=30), 8000, CFG)
    assert b.badge_state == "verified"
    assert b.reference_kop == 10000 and b.verified_pct == 20
    assert b.n_points == 30


def test_verified_provisional_short_history():
    """8 днів історії (≥4, <10) → зелений попередній."""
    b = compute_badge(days([10000] * 8), D0 + timedelta(days=8), 8000, CFG)
    assert b.badge_state == "verified_provisional"
    assert b.verified_pct == 20


def test_pumped_price_inflated():
    """20 днів по 100, потім накачали до 200 і «знижка» до 150 → жовтий (реально не нижче)."""
    hist = days([10000] * 20) + days([20000], start=D0 + timedelta(days=20))
    b = compute_badge(hist, D0 + timedelta(days=21), 15000, CFG, old_kop=20000)
    assert b.badge_state == "pumped"
    assert b.declared_pct == 25 and b.verified_pct is not None and b.verified_pct < 0
    assert b.reference_kop == 10000


def test_insufficient_vs_declared():
    """<4 валідних точок: без старої → insufficient; зі старою → нейтральний declared."""
    short = days([10000] * 3)
    assert compute_badge(short, D0 + timedelta(days=3), 8000, CFG).badge_state == "insufficient_history"
    b = compute_badge(short, D0 + timedelta(days=3), 8000, CFG, old_kop=12000)
    assert b.badge_state == "declared" and b.declared_pct is not None


def test_oos_points_excluded_from_reference():
    """OOS-точки з нижчою ціною НЕ стають базою (§5.2) — інакше фальшивий pumped."""
    hist = days([10000] * 6) + days([3000] * 6, in_stock=False, start=D0 + timedelta(days=6))
    b = compute_badge(hist, D0 + timedelta(days=12), 9000, CFG)
    assert b.reference_kop == 10000            # не 3000 (OOS виключено)
    assert b.badge_state == "verified_provisional" and b.verified_pct == 10


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
