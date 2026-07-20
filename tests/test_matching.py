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


def test_samsung_short_plus_full_takes_full():
    """Foxtrot-стиль: коротка модель інлайн + повний артикул у дужках → повний."""
    assert extract_mpn("Смартфон SAMSUNG SM-S942B Galaxy S26 12/256Gb Black (SM-S942BZKGEUC)") \
        == "SM-S942BZKGEUC"


def test_samsung_short_only_is_ambiguous():
    """Коротка модель БЕЗ повного артикула спільна для варіантів памʼяті/кольору —
    ключем бути не може (перезлиття 256GB з 512GB); чесніше None."""
    assert extract_mpn("Смартфон SAMSUNG SM-S942B Galaxy S26 12/512Gb Blue") is None


def test_apple_code_in_parens():
    assert extract_mpn("Смартфон Apple iPhone 17 256GB Black (MG6J4)") == "MG6J4"


def test_apple_code_with_slash():
    assert extract_mpn("Apple iPhone 17 256GB Black (MG6J4AF/A)") == "MG6J4AF/A"


def test_last_paren_token_wins():
    # артикул зазвичай в останніх дужках; перші дужки — колір/памʼять
    assert extract_mpn("Xiaomi Redmi Note 15 (8/256GB) Black (2312DRA50G)") == "2312DRA50G"


# ── інлайн-артикул: телевізори (розвідка 2026-07-20, назви з прод-бази) ───────

def test_tv_inline_lg():
    assert extract_mpn("Телевізор LG 43UA75006LA") == "43UA75006LA"


def test_tv_inline_samsung():
    assert extract_mpn("Телевізор SAMSUNG QE50Q7FAAUXUA") == "QE50Q7FAAUXUA"


def test_tv_same_model_across_stores_gets_one_key():
    """Суть фічі: 4 крамниці пишуть той самий телевізор по-різному — ключ мусить збігтись.
    До фіксу це були 4 окремі картки (offers_n=1) по 16 499 ₴ кожна."""
    titles = [
        "Телевізор LED LG 43UA75006LA (Smart TV, Wi-Fi, 3840x2160)",   # KTC
        "Телевізор LG 43UA75006LA",                                     # Citrus / Moyo
        'Телевізор LG 43" 43UA75006LA',                                 # Rozetka
    ]
    keys = {extract_mpn(t) for t in titles}
    assert keys == {"43UA75006LA"}, keys


def test_tv_qled_haier_across_stores():
    keys = {extract_mpn(t) for t in [
        'Телевізор Haier QLED 50" H50S80FUX',
        "Телевізор HAIER H50S80FUX",
        "Телевізор QLED Haier H50S80FUX (Google TV, Wi-Fi, 3840x2160)",
    ]}
    assert keys == {"H50S80FUX"}, keys


# ── Acer: артикул із КРАПКАМИ, і в дужках, і інлайн ───────────────────────────

def test_acer_dotted_code_in_parens():
    assert extract_mpn("Ноутбук Acer Extensa 15 EXO15-41 (NX.EL5EU.003)") == "NX.EL5EU.003"


def test_acer_dotted_code_inline():
    assert extract_mpn("Ноутбук Acer Aspire Lite AL16-54P-56ES NX.DK6EU.008 Silver") \
        == "NX.DK6EU.008"


# ── інлайн НЕ пересилює дужки й НЕ хапає серію ────────────────────────────────

def test_paren_wins_over_inline():
    """Дужковий артикул надійніший — інлайн вмикається лише за його відсутності."""
    assert extract_mpn("Ноутбук HP 15-fc0312ua ABCD1234 (CS8A2EA)") == "CS8A2EA"


def test_short_series_without_config_rejected():
    """«65B5» — серія, СПІЛЬНА для комплектацій; ключем бути не може (перезлиття).
    Так само «X1504VA» без конфігурації."""
    assert extract_mpn("Телевізор LG OLED 65B5") is None
    assert extract_mpn("Ноутбук ASUS Vivobook 15 X1504VA") is None


def test_resolution_and_brand_not_mpn():
    assert extract_mpn("Телевізор Samsung QLED 4K 3840x2160") is None
    assert extract_mpn("Телевізор SAMSUNG QLED") is None


def test_tv_sizes_stay_distinct():
    """Різні діагоналі однієї лінійки — РІЗНІ товари; ключі мусять різнитись."""
    a = extract_mpn('Телевізор Haier QLED 43" H43S80FUX')
    b = extract_mpn('Телевізор Haier QLED 50" H50S80FUX')
    assert a and b and a != b


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
