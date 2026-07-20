"""Юніт-тести категоризації за URL (§2.6). Чистий, без БД.

Запуск:  python tests/test_taxonomy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from taxonomy import categorize, refine_category, SEED_CATEGORIES  # noqa: E402


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


def test_refine_accessories_out_of_smartfony():
    # реальні контамінанти з Brain-департаменту «Смартфони та зв'язок»
    assert refine_category("smartfony", "Дата кабель USB 2.0 AM to USB-C 1.0m 3A Baseus (CATKLF-BG1)") == "aksesuary"
    assert refine_category("smartfony", "Навушники JBL Wave Beam 2 Black (JBLWBEAM2BLK)") == "audio"
    assert refine_category("smartfony", "Навушники Apple AirPods 4 (MXP63ZE/A)") == "audio"
    assert refine_category("smartfony", "Зовнішній акумулятор Baseus 20000mAh") == "aksesuary"
    assert refine_category("smartfony", "Чохол-книжка Samsung Galaxy A55") == "aksesuary"


def test_refine_keeps_real_phones():
    # справжні телефони з того ж лістинга — лишаються смартфонами
    assert refine_category("smartfony", "Мобільний телефон Xiaomi Redmi Note 15 Pro 8/256GB Black (1183684)") == "smartfony"
    assert refine_category("smartfony", "Смартфон XIAOMI REDMI A7 Pro 4/128GB Palm Green") == "smartfony"
    assert refine_category("smartfony", "Motorola G06 4/64GB Tapestry (PBA20002UA)") == "smartfony"


def test_refine_only_device_categories():
    # не-пристроєву базу (зоо) не чіпає, навіть якщо слово збіглось
    assert refine_category("koty-suhyi-korm", "Корм з кабелем у назві (артефакт)") == "koty-suhyi-korm"
    assert refine_category("inshe", "Навушники") == "inshe"


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
