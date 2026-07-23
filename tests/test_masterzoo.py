"""Golden-тест адаптера MasterZoo на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Касета знята з КЛАСИЧНОГО шаблону крізь пройдений анти-бот-челендж (без куки
challenge_passed сервер віддає порожняк або staging Next.js-шелл без цін — саме
тому крамниця в mode="render"). Стережемо: формат цін «2 837.00 грн»
(пробіл-тисячник + крапка-десяткова → 283700 коп), назву з title-атрибута
(текст лінка має хвости пробілів), відносні href/src.

Запуск:  python -m pytest tests/test_masterzoo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.masterzoo import MasterzooAdapter               # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "masterzoo_listing.html"), encoding="utf-8") as f:
        return MasterzooAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_space_thousands_dot_decimals():
    """«1 999.00 грн» / «2 837.00 грн» → 199900 / 283700 коп."""
    i = next(x for x in _items() if "cat-chow-urinary" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (199900, 283700), (i.price_now_kop, i.price_old_kop)


def test_plain_card_no_old():
    i = next(x for x in _items() if "royal-canin-gastrointestinal" in x.external_ref)
    assert i.price_old_kop is None
    assert i.price_now_kop == 33900, i.price_now_kop


def test_title_from_attr_without_whitespace_tails():
    i = next(x for x in _items() if "cat-chow-urinary" in x.external_ref)
    assert i.title == "Cухий корм для котів Cat Chow Urinary 15 кг - курка", i.title
    assert i.title == i.title.strip()


def test_relative_href_and_img_glued():
    for i in _items():
        assert i.external_ref.startswith("https://masterzoo.ua/ua/catalog/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref
        assert i.image_url is not None and i.image_url.startswith("https://masterzoo.ua/content/"), i.image_url


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
