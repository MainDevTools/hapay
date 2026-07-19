"""Тести MPN-екстрактора (T15) — чисті, без БД.

Головне: ПЕРЕзлиття = брехня на картці, тому перевіряємо не лише «знаходить»,
а й «НЕ знаходить там, де здалося б» (памʼять, EAN, стоп-слова) і «НЕ зливає»
регіональні суфікси (пастка AUXUA).

Запуск:  python tests/test_matching.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from matching import extract_mpn          # noqa: E402


# ── знаходить ─────────────────────────────────────────────────────────────────

def test_samsung_in_parens():
    assert extract_mpn("Samsung Galaxy A37 5G 8/256GB Awesome Lavender (SM-A376BDGGEUC)") \
        == "SM-A376BDGGEUC"


def test_samsung_inline_without_parens():
    assert extract_mpn("Смартфон Samsung Galaxy A57 5G SM-A576BZVDEUC 8/256GB") \
        == "SM-A576BZVDEUC"


def test_apple_code_in_parens():
    assert extract_mpn("Смартфон Apple iPhone 17 256GB Black (MG6J4)") == "MG6J4"


def test_apple_code_with_slash():
    assert extract_mpn("Apple iPhone 17 256GB Black (MG6J4AF/A)") == "MG6J4AF/A"


def test_last_paren_token_wins():
    # артикул зазвичай в останніх дужках; перші дужки — колір/памʼять
    assert extract_mpn("Xiaomi Redmi Note 15 (8/256GB) Black (2312DRA50G)") == "2312DRA50G"


# ── НЕ знаходить (форм-фільтри) ───────────────────────────────────────────────

def test_memory_specs_rejected():
    assert extract_mpn("Samsung Galaxy TAB (256GB)") is None
    assert extract_mpn("Смартфон Poco X8 Pro (8/256GB)") is None


def test_pure_digits_ean_rejected():
    assert extract_mpn("Frosch Aloe Vera 5 л (4001499962561)") is None


def test_stop_words_rejected():
    assert extract_mpn("Телевізор LG 55 (OLED) (NEW)") is None


def test_cyrillic_and_petfood_rejected():
    assert extract_mpn("Royal Canin Yorkshire Terrier Adult 1,5 кг (курка)") is None
    assert extract_mpn("Сухий корм Brit Premium Adult M") is None


def test_none_and_empty():
    assert extract_mpn(None) is None
    assert extract_mpn("") is None


# ── НЕ зливає (пастка суфіксів) ───────────────────────────────────────────────

def test_regional_suffixes_stay_distinct():
    """SM-…EUC ≠ SM-…AUXUA: різні суфікси = різні ключі (недозлиття безпечне)."""
    eu = extract_mpn("Samsung Galaxy A37 (SM-A376BDGGEUC)")
    ua = extract_mpn("Samsung Galaxy A37 (SM-A376BDGGAUXUA)")
    assert eu and ua and eu != ua


def test_deterministic():
    t = "Samsung Galaxy S25 Edge 5G 12/512GB TITANIUM (SM-S937BZTGEUC)"
    assert extract_mpn(t) == extract_mpn(t) == "SM-S937BZTGEUC"


def _main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v) and getattr(v, "__module__", None) == __name__]
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
