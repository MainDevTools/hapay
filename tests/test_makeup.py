"""Golden-тест адаптера MakeUp на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Касета знята крізь aws-waf-token браузерної сесії (без токена категорії віддають
0KB — тому крамниця в mode=render). Стережемо: селекцію по BEM-префіксу
(«ProductCard__title shop_hash» — хеш-суфікс міняється білдом), склейку назви
title+subTitle (subTitle несе бренд+MPN), пару Price__priceCurrent/priceOld.

Запуск:  python -m pytest tests/test_makeup.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.makeup import MakeupAdapter                     # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "makeup_listing.html"), encoding="utf-8") as f:
        return MakeupAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_title_glued_from_type_and_model():
    """title («Фен для волосся») + subTitle («Philips … BHC010/10») → одна назва."""
    i = next(x for x in _items() if x.price_old_kop is None)
    assert i.title == "Фен для волосся Philips Essential Care BHC010/10", i.title
    assert "BHC010" in i.title            # MPN із subTitle не загубився


def test_discount_pair():
    i = next(x for x in _items() if x.price_old_kop is not None)
    assert (i.price_now_kop, i.price_old_kop) == (223500, 263000), (i.price_now_kop, i.price_old_kop)


def test_plain_card_no_old():
    i = next(x for x in _items() if "Philips Essential" in x.title)
    assert i.price_old_kop is None
    assert i.price_now_kop == 69900, i.price_now_kop


def test_ref_canonical():
    for i in _items():
        assert i.external_ref.startswith("https://makeup.com.ua/ua/product/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
