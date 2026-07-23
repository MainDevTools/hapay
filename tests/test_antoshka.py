"""Golden-тест адаптера Antoshka на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Головна пастка — promo-бейджі «-22%» ВСЕРЕДИНІ цінових контейнерів: текст
контейнера цілком дає «-22% 12 899 ₴», звідки парсер вихопив би 22 грн. Адаптер
мусить читати лише внутрішні вузли (<p> у __price, <span> у __price-old).

Запуск:  python -m pytest tests/test_antoshka.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.antoshka import AntoshkaAdapter                 # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "antoshka_listing.html"), encoding="utf-8") as f:
        return AntoshkaAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_promo_badge_not_parsed_as_price():
    """«9 999 ₴» + бейдж «-22%» → 999900/1289900 коп, НЕ 2200."""
    i = next(x for x in _items() if "anex-air-x" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (999900, 1289900), (i.price_now_kop, i.price_old_kop)
    for x in _items():
        assert x.price_now_kop != 2200 and x.price_old_kop != 2200


def test_plain_card_no_old():
    i = next(x for x in _items() if "cybex-beezy" in x.external_ref)
    assert i.price_old_kop is None
    assert i.price_now_kop == 1249000, i.price_now_kop


def test_title_from_img_alt():
    i = next(x for x in _items() if "cybex-beezy" in x.external_ref)
    assert i.title == "Прогулянкова коляска Cybex Beezy Fog Grey", i.title


def test_ref_canonical():
    for i in _items():
        assert i.external_ref.startswith("https://antoshka.ua/uk/"), i.external_ref
        assert i.external_ref.endswith(".html")
        assert "?" not in i.external_ref and "#" not in i.external_ref


def test_image_pointer_only():
    for i in _items():
        assert i.image_url is not None and i.image_url.startswith("https://antoshka.ua/media/"), i.image_url


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
