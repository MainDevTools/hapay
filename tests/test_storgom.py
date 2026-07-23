"""Golden-тест адаптера Storgom на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Одна акційна і дві звичайні — і це не для симетрії. У Storgom ціна акційної картки
живе в `.new-price`, а звичайної — у БЕЗКЛАСОВОМУ `<div>` усередині `.price`; водночас
`.price` як ціле СКЛЕЮЄ стару ціну, бейдж «-2 100 ₴» і нову в один рядок (перша проба
чесно віддала now=89992100689900 копійок). Тож обидва шляхи мусять бути в касеті.

Назви беруться з JSON-LD ItemList (чистіші за alt), тому LD у касеті обрізано до тих
самих 3 позицій — тест ловить і розсинхрон LD↔картки.

Запуск:  python -m pytest tests/test_storgom.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.storgom import StorgomAdapter                   # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "storgom_listing.html"), encoding="utf-8") as f:
        return StorgomAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_discount_card_takes_new_not_glued():
    """Акційна картка: now з `.new-price`, old лише з `<s>` — НЕ склейка всіх чисел."""
    i = next(x for x in _items() if "makita-hr2470" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (689900, 899900), (i.price_now_kop, i.price_old_kop)


def test_plain_card_classless_div_not_lost():
    """Звичайна картка: ціна в безкласовому div — її теж мусимо взяти, old=None."""
    i = next(x for x in _items() if "procraft-190392" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (247500, None), (i.price_now_kop, i.price_old_kop)


def test_title_from_ld_itemlist():
    """Назва — з JSON-LD ItemList (з артикулом продавця в дужках, як дає крамниця)."""
    i = next(x for x in _items() if "procraft-190392" in x.external_ref)
    assert i.title == "Перфоратор PROCRAFT BH1400 (014001)", i.title


def test_ref_canonical_and_url_absolute():
    for i in _items():
        assert i.external_ref.startswith("https://storgom.ua/ua/product/"), i.external_ref
        assert i.external_ref == i.external_ref.lower()
        assert "?" not in i.external_ref and "#" not in i.external_ref
        assert i.url.startswith("https://storgom.ua/"), i.url


def test_image_pointer_only():
    """Фото — лише вказівник (інваріант B): URL, не байти; службові /theme/ відсіяні."""
    for i in _items():
        if i.image_url is not None:
            assert i.image_url.startswith("http"), i.image_url
            assert "/theme/" not in i.image_url


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
