"""Golden-тест адаптера Dnipro-M на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Дві пастки, обидві стрелили на розвідці й ЗАШИТІ в касету:
1. Незакритий <template> перед сіткою: за HTML5 вміст template живе поза головним
   деревом — css() бачить нуль карток при 23 сирих (касета-фрагмент парсилась,
   жива сторінка — ні). Касета навмисно загорнута так само.
2. price_old заповнена ЗАВЖДИ: для безакційних товарів дорівнює price_new —
   сирою вона тегувала б весь асортимент фальш-знижками 0%.

Запуск:  python -m pytest tests/test_dniprom.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.dniprom import DniproMAdapter                   # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "dniprom_listing.html"), encoding="utf-8") as f:
        return DniproMAdapter().extract(f.read())


def test_template_wrapper_does_not_hide_cards():
    """Пастка 1: картки всередині незакритого <template> мусять видобуватись."""
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_discount_from_encoded_json():
    """price='{&quot;price_new&quot;:&quot;2997&quot;…}' → 299700/420000 коп."""
    i = next(x for x in _items() if "cd-200bc" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (299700, 420000), (i.price_now_kop, i.price_old_kop)


def test_equal_old_price_becomes_none():
    """Пастка 2: price_old == price_new → old=None, не фальш-знижка 0%."""
    i = next(x for x in _items() if "cd-218q" in x.external_ref)
    assert i.price_old_kop is None, i.price_old_kop
    assert i.price_now_kop == 159000, i.price_now_kop


def test_title_and_ref():
    i = next(x for x in _items() if "cd-200bc" in x.external_ref)
    assert i.title == "Акумуляторний дриль-шуруповерт Dnipro-M CD-200BC KIT", i.title
    for x in _items():
        assert x.external_ref.startswith("https://dnipro-m.ua/tovar/"), x.external_ref
        assert "?" not in x.external_ref and "#" not in x.external_ref


def test_image_from_photos_json():
    for i in _items():
        assert i.image_url is not None and i.image_url.startswith("https://static.dnipro-m.ua/"), i.image_url


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
