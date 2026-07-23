"""Golden-тест адаптера Med-magazin на ОБРІЗАНІЙ касеті (§8.8): 3 картки сітки + 1 слайдер.

Слайдер-картка в касеті — НЕ для об'єму: клас `product-box-container` носять і
слайдери «рекомендоване» (на живій сторінці їх 37 проти 20 карток сітки), а
рекомендоване — товари З ІНШИХ категорій. Якби адаптер їх брав, ми тегували б
чужі товари нашою категорією — тихо і правдоподібно. Тест мусить довести, що
scroller-item ігнорується: 4 картки в касеті → рівно 3 позиції на виході.

Запуск:  python -m pytest tests/test_medmagazin.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.medmagazin import MedmagazinAdapter             # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "medmagazin_listing.html"), encoding="utf-8") as f:
        return MedmagazinAdapter().extract(f.read())


def test_slider_card_ignored():
    """4 картки в касеті (3 сітка + 1 scroller-item) → рівно 3 позиції."""
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_discount_card_current_and_old():
    i = next(x for x in _items() if "item_n42533" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (148900, 223200), (i.price_now_kop, i.price_old_kop)
    assert i.title == "Автоматичний тонометр B.Well MED-50 (Швейцарія)", i.title


def test_plain_card_no_old():
    i = next(x for x in _items() if i_has_no_old(x))
    assert i.price_old_kop is None

def i_has_no_old(x):
    return x.price_old_kop is None


def test_ref_canonical():
    for i in _items():
        assert i.external_ref.startswith("https://med-magazin.ua/ua/item_"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


def test_image_pointer_only():
    """Фото — лише вказівник (інваріант B), на CDN крамниці."""
    for i in _items():
        if i.image_url is not None:
            assert i.image_url.startswith("http"), i.image_url


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
