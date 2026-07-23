"""Golden-тест адаптера Fotosale на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Стережемо: пару .main-price/.old-price (стара лише на акційних; буває без
пробілів-роздільників — «69999»), чисту назву з a.name (img[title] дублює бренд),
ленивe зображення (URL у data-src, у src — заглушка).

Запуск:  python -m pytest tests/test_fotosale.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.fotosale import FotosaleAdapter                 # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "fotosale_listing.html"), encoding="utf-8") as f:
        return FotosaleAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_discount_card_with_nospace_old_price():
    """Стара ціна «69999» (без роздільників) мусить розпарситись у 6 999 900 коп."""
    i = next(x for x in _items() if "product_n65220" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (6499900, 6999900), (i.price_now_kop, i.price_old_kop)


def test_plain_card_no_old():
    i = next(x for x in _items() if "product_n66086" in x.external_ref)
    assert i.price_old_kop is None
    assert i.price_now_kop == 21999900, i.price_now_kop


def test_title_from_name_link_not_img():
    """a.name — без брендового префікса img[title] («Canon Фотокамера Canon…»)."""
    i = next(x for x in _items() if "product_n66086" in x.external_ref)
    assert i.title == "Фотокамера Canon EOS R3 (4895C014) (UA)", i.title


def test_image_from_lazy_data_src():
    for i in _items():
        assert i.image_url is not None and i.image_url.startswith("https://fotosale.ua/images/"), i.image_url


def test_ref_canonical():
    for i in _items():
        assert i.external_ref.startswith("https://fotosale.ua/ua/product_"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
