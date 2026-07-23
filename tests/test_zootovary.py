"""Golden-тест адаптера Zootovary на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Головне, що стережемо — КОМА-ТИСЯЧНИК: «2,739 ₴» = 2739 грн. Глобальний
parse_price_to_kop трактує кому як десяткову (вірно для інших крамниць), тож
без локального чищення ціна тихо стискається в ~100 разів (впіймано на
валідації: 274 коп замість 2739 грн + 5 «нісенітниць» old<now). Другий кейс —
«від N ₴» (мінімум вагових варіантів) із роздільником у старій ціні.

Запуск:  python -m pytest tests/test_zootovary.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.zootovary import ZootovaryAdapter               # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "zootovary_listing.html"), encoding="utf-8") as f:
        return ZootovaryAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_comma_is_thousands_not_decimal():
    """«2,739 ₴» / «4,039 ₴» → 2739 грн / 4039 грн (НЕ 2.74 / 4.04)."""
    i = _items()[0]
    assert (i.price_now_kop, i.price_old_kop) == (273900, 403900), (i.price_now_kop, i.price_old_kop)


def test_vid_prefix_and_comma_in_old():
    """«від 867 ₴» → 867 грн; стара «1,020 ₴» → 1020 грн."""
    i = _items()[1]
    assert (i.price_now_kop, i.price_old_kop) == (86700, 102000), (i.price_now_kop, i.price_old_kop)


def test_old_greater_than_now():
    for i in _items():
        assert i.price_old_kop is None or i.price_old_kop > i.price_now_kop


def test_image_glued_from_relative_data_original():
    """src — заглушка pixel_trans.png; справжній шлях у data-original без хоста."""
    for i in _items():
        assert i.image_url is not None and i.image_url.startswith("https://zootovary.ua/getimage/"), i.image_url
        assert "pixel_trans" not in i.image_url


def test_ref_canonical():
    for i in _items():
        assert i.external_ref.startswith("https://zootovary.ua/uk/"), i.external_ref
        assert "-p-" in i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
