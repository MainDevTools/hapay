"""Юніт-тести ядра «Наш вибір» v1 (S9) — синтетика, без БД.

Стережемо: домінацію ціни; перекидання вибору чесністю; free_from-межу доставки;
групу-одиначку (None); нейтральні 0.5 для крамниці без подій (Лаплас); рівні
ефективні ціни (span=0); out-of-stock як фільтр; no_delivery_data-прапорець.

Запуск:  python -m pytest tests/test_choice.py
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from choice.core import Offer, Weights, effective_kop, honesty_score, pick  # noqa: E402

W = Weights(Decimal("0.70"), Decimal("0.25"), Decimal("0.05"), Decimal(1))


def _o(store, price, in_stock=True, free_from=None, base=None,
       pumped=0, total=0, pickup=False):
    return Offer(store, price, in_stock, free_from, base, pumped, total, pickup)


def test_price_dominates_all_else_equal():
    r = pick([_o("A", 100_00), _o("B", 150_00)], W)
    assert r["our_choice"] == "A"
    assert r["savings_kop"] == 50_00


def test_honesty_flips_choice_when_prices_close():
    """Дешевша на 1% крамниця-«накачувач» (9/10 pumped) програє чесній."""
    r = pick([_o("Pumper", 99_00, pumped=9, total=10),
              _o("Honest", 100_00, pumped=0, total=10)], W)
    assert r["our_choice"] == "Honest", r


def test_free_from_boundary_changes_effective_price():
    """Ціна 900 грн < free_from 1000 → +80 грн доставки; ефективно дорожча за 950-грн
    конкурента з безкоштовною доставкою."""
    a = _o("A", 900_00, free_from=1000_00, base=80_00)
    b = _o("B", 950_00, free_from=500_00, base=80_00)
    assert effective_kop(a) == (980_00, False)
    assert effective_kop(b) == (950_00, False)
    assert pick([a, b], W)["our_choice"] == "B"


def test_no_delivery_rule_flagged_not_penalized():
    e, nodata = effective_kop(_o("X", 500_00))
    assert (e, nodata) == (500_00, True)
    r = pick([_o("X", 500_00), _o("Y", 600_00, free_from=None, base=0)], W)
    x = next(c for c in r["candidates"] if c["store"] == "X")
    assert x["no_delivery_data"] is True


def test_laplace_neutral_half_for_no_events():
    assert honesty_score(_o("N", 1, total=0), Decimal(1)) == Decimal("0.5")


def test_single_candidate_returns_none():
    assert pick([_o("Solo", 100_00)], W) is None
    assert pick([_o("A", 100_00), _o("B", 90_00, in_stock=False)], W) is None


def test_out_of_stock_filtered():
    r = pick([_o("Cheap", 50_00, in_stock=False), _o("A", 100_00), _o("B", 110_00)], W)
    assert r["our_choice"] == "A"
    assert all(c["store"] != "Cheap" for c in r["candidates"])


def test_equal_effective_prices_span_zero():
    r = pick([_o("A", 100_00), _o("B", 100_00)], W)
    assert r["savings_kop"] == 0
    assert all(c["components"]["price_score"] == 1.0 for c in r["candidates"])


def test_components_visible_and_sum_matches():
    r = pick([_o("A", 100_00, pickup=True, total=4, pumped=1), _o("B", 120_00)], W)
    for c in r["candidates"]:
        comp = c["components"]
        recomputed = 0.70 * comp["price_score"] + 0.25 * comp["honesty_score"] + comp["pickup_bonus"]
        assert abs(recomputed - c["score"]) < 0.001, c


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
