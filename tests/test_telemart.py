"""Golden-тест адаптера Telemart на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Дві акційні картки й одна звичайна — і це не для симетрії. Модифікатор `_new`
крамниця ставить ЛИШЕ на акційних товарах; у звичайного ціна лежить у голому
`.product-cost`. Перша версія адаптера брала тільки `_new` і тихо віддавала 25
позицій із 48 — усі зі знижкою. Виглядало б правдоподібно («Telemart торгує
переважно акційним»), тож помітити було б нічим, окрім лічильника. Тому звичайна
картка в касеті обов'язкова.

Запуск:  python tests/test_telemart.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.telemart import TelemartAdapter                # noqa: E402
from matching import extract_mpn                              # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "telemart_listing.html"), encoding="utf-8") as f:
        return TelemartAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_plain_card_without_discount_is_not_lost():
    """Товар БЕЗ знижки має голий `.product-cost` — його теж мусимо взяти."""
    i = next(x for x in _items() if "xiaomi-43" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (1049900, None), (i.price_now_kop, i.price_old_kop)


def test_discount_card_takes_new_not_old():
    """Акційна картка: `_new` — поточна, `_old` — стара. Не навпаки.

    Клас `product-cost` носять ТРИ вузли (стара, поточна, бейдж «-14%»), тож
    селектор без модифікатора віддав би стару ціну як поточну — тихо.
    """
    i = next(x for x in _items() if "43pus700012" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (1499900, 1749900), (i.price_now_kop, i.price_old_kop)


def test_discount_badge_never_read_as_price():
    """Бейдж «-14%» теж має клас product-cost. Якби його прочитали як ціну,
    вийшло б 14 копійок."""
    for i in _items():
        assert i.price_now_kop > 100000, i.price_now_kop      # усі три дорожчі за 1000 грн
        assert i.price_old_kop is None or i.price_old_kop > i.price_now_kop


def test_image_is_product_photo_not_ui_icon():
    """Перше <img> у картці — іконка «безкоштовна доставка» з /theme/, а не товар."""
    for i in _items():
        assert i.image_url and "/theme/" not in i.image_url, i.image_url
        assert i.image_url.startswith("https://"), i.image_url


def test_title_from_attribute_keeps_quotes():
    """У назві є дюйми (`43"`), які в тексті подані як entity — беремо атрибут title."""
    i = next(x for x in _items() if "43pus700012" in x.external_ref)
    assert i.title == 'Телевизор Philips 43" 43PUS7000/12 Black', i.title
    assert extract_mpn(i.title) == "43PUS7000/12"


def test_ref_is_path_only():
    for i in _items():
        assert i.external_ref.startswith("/products/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
