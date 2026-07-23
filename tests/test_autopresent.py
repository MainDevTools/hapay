"""Golden-тест адаптера Autopresent на ОБРІЗАНІЙ касеті (§8.8).

Касета навмисно містить картку «спецпропозиції» ПОЗА .main-products (товар чужої
категорії — сигналізація в лістингу реєстраторів) + 2 картки головної сітки.
Тест доводить: спецпропозиція ігнорується (скоуп .main-products), біті alt
(PHP Notice в атрибуті) не течуть у назву, пара price-new/price-old парситься,
а price-tax («Без ПДВ:…») не задвоює числа.

Запуск:  python -m pytest tests/test_autopresent.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.autopresent import AutopresentAdapter           # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "autopresent_listing.html"), encoding="utf-8") as f:
        return AutopresentAdapter().extract(f.read())


def test_special_offer_outside_grid_ignored():
    """3 product-thumb у касеті (1 спецпропозиція + 2 сітка) → рівно 2 позиції."""
    items = _items()
    assert len(items) == 2, len(items)
    for i in items:
        assert "avtosignalizacii" not in i.external_ref, i.external_ref


def test_discount_pair_and_no_tax_doubling():
    i = _items()[0]
    assert (i.price_now_kop, i.price_old_kop) == (19900, 39900), (i.price_now_kop, i.price_old_kop)


def test_no_php_notice_in_title():
    """alt битий («Undefined index: model…») — назва мусить іти з img[title]."""
    for i in _items():
        assert "Notice" not in i.title and "Undefined" not in i.title, i.title
        assert i.title


def test_old_greater_than_now():
    for i in _items():
        assert i.price_old_kop is None or i.price_old_kop > i.price_now_kop


def test_ref_canonical():
    for i in _items():
        assert i.external_ref.startswith("https://autopresent.com.ua/ua/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
