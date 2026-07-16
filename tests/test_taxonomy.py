"""Юніт-тести категоризації за URL (§2.6). Чистий, без БД.

Запуск:  python tests/test_taxonomy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from taxonomy import categorize, SEED_CATEGORIES  # noqa: E402


def test_pethouse_urls():
    assert categorize("https://pethouse.ua/ua/shop/koshkam/suhoi-korm/royalcanin/royal-canin-sterilised") == "koty-suhyi-korm"
    assert categorize("https://pethouse.ua/ua/shop/sobakam/suhoi-korm/purina/x") == "psy-suhyi-korm"
    assert categorize("https://pethouse.ua/ua/shop/koshkam/konservi/x") == "koty-konservy"
    assert categorize("https://pethouse.ua/ua/shop/sobakam/shampuni/x") == "psy-shampuni"


def test_petchoice_urls():
    assert categorize("https://petchoice.ua/sobakam/suxoj-korm/royal-canin-maxi-adult") == "psy-suhyi-korm"
    assert categorize("https://petchoice.ua/sobakam/oshejniki/collar-waudog-led") == "amunitsiya"


def test_fallback_inshe():
    assert categorize("https://x.ua/shop/igrashki/myach") == "inshe"
    assert categorize("") == "inshe"
    assert categorize("https://x.ua/koshkam/") == "inshe"        # тварина без типу


def test_ammo_wins_over_animal():
    assert categorize("https://x.ua/sobakam/oshejniki/x") == "amunitsiya"


def test_all_categorize_slugs_are_seeded():
    seeded = {s for s, _ in SEED_CATEGORIES}
    for url in ("koshkam/suhoi-korm", "sobakam/konservi", "koshkam/shampuni", "oshejniki", "igrashki"):
        assert categorize("https://x/" + url) in seeded


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL  {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
