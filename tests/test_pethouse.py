"""Golden-тест екстрактора Pethouse на ОБРІЗАНІЙ реальній касеті (§8.8).

Запуск:  python tests/test_pethouse.py   (або через pytest)
Потребує selectolax (requirements.txt).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.pethouse import PethouseAdapter          # noqa: E402
from adapters.base import parse_price_to_kop, canon_ref, slugify  # noqa: E402

CASSETTE = os.path.join(os.path.dirname(__file__), "cassettes", "pethouse_akcii.html")


def _items():
    with open(CASSETTE, encoding="utf-8") as f:
        return PethouseAdapter().extract(f.read())


def _by_variant(items, ref_tail):
    return next(i for i in items if i.external_ref.endswith(ref_tail))


# ---- екстрактор на касеті ----

def test_counts():
    items = _items()
    assert len(items) == 9, len(items)                       # 2 товари × варіанти
    assert len({i.url for i in items}) == 2


def test_no_duplicate_refs():
    items = _items()
    assert len({i.external_ref for i in items}) == len(items)


def test_now_below_old_where_discounted():
    for i in _items():
        if i.price_old_kop is not None:
            assert i.price_now_kop < i.price_old_kop, i


def test_kopecks_exact_royal_canin_4kg():
    i = _by_variant(_items(), "royal-canin-sterilised#v=4-кг")
    assert i.price_now_kop == 170000        # 1 700,00
    assert i.price_old_kop == 200000        # 2 000,00
    assert i.discount_pct == 15
    assert i.in_stock is True
    assert i.variant_note == "4 кг"
    assert i.unit_text == "425 грн/кг"
    assert i.image_url and i.image_url.startswith("http")
    assert "Royal Canin Sterilised" in i.title and "4 кг" in i.title


def test_kopecks_exact_royal_canin_10kg():
    i = _by_variant(_items(), "royal-canin-sterilised#v=10-кг")
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (360000, 480000, 25)


def test_variant_without_discount_has_none_old():
    """Не всі варіанти зі знижкою — екстрактор віддає old=None, не 0/помилку."""
    i = _by_variant(_items(), "turkey-#v=3-кг")
    assert i.price_now_kop == 142600 and i.price_old_kop is None and i.discount_pct is None


def test_all_refs_are_per_variant():
    for i in _items():
        assert "#v=" in i.external_ref


def test_urls_absolute():
    """URL — абсолютні (для посилань «відкрити в крамниці»); external_ref — зі ВІДНОСНОГО (стабільний ключ)."""
    for i in _items():
        assert i.url.startswith("https://pethouse.ua/"), i.url
        assert i.external_ref.startswith("/ua/shop/"), i.external_ref


# ---- парсер копійок (§4.8) ----

def test_parse_price():
    assert parse_price_to_kop("2 000,00") == 200000
    assert parse_price_to_kop("1 700,00 ₴") == 170000
    assert parse_price_to_kop("212,50") == 21250
    assert parse_price_to_kop("1 040,00") == 104000     # nbsp-тисячі
    assert parse_price_to_kop("299") == 29900
    assert parse_price_to_kop("від 499 грн") == 49900        # число; «від» обробляє викликач
    assert parse_price_to_kop("—") is None
    assert parse_price_to_kop("") is None
    assert parse_price_to_kop(None) is None


def test_canon_and_slug():
    assert canon_ref("/UA/Shop/Korm/?utm=x#f") == "/ua/shop/korm"
    assert slugify("1,5 кг") == "1-5-кг"


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
