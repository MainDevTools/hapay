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


def test_refine_splits_appliances_from_pobut():
    """Кроки 1–2: холодильники й пральні з широкого лістинга → власні полиці."""
    assert refine_category("pobut-tehnika", "Холодильник Samsung RB34C670EB1/UA No Frost") == "holodylnyky"
    assert refine_category("pobut-tehnika", "Холодильник BOSCH KGN39VLCT") == "holodylnyky"
    assert refine_category("pobut-tehnika", "Пральна машина LG F2WV3S7S6TE") == "pralni-mashyny"
    assert refine_category("pobut-tehnika", "Прально-сушильна машина Candy RO4 1274DWMT") == "pralni-mashyny"
    assert refine_category("pobut-tehnika", "Посудомийна машина Bosch SMS4HMW00E") == "posudomyiky"
    assert refine_category("pobut-tehnika", "Сушильна машина Samsung DV90T6240LE/UA") == "sushylni-mashyny"


def test_refine_pralna_sushylna_combo_stays_washer():
    """«Прально-сушильна» — комбо, що ПЕРЕ: лишається в пральних (пральні перевіряються
    раніше за сушильні у кортежі). Інакше комбо роздвоїлось би між полицями."""
    assert refine_category("pobut-tehnika", "Прально-сушильна машина Candy RO4 1274DWMT") == "pralni-mashyny"


def test_refine_keeps_other_appliances_in_pobut():
    """Дрібне (мультиварки/праски/…) поки лишається в pobut-tehnika (наступні кроки)."""
    assert refine_category("pobut-tehnika", "Мультиварка Redmond RMC-M90") == "pobut-tehnika"
    assert refine_category("pobut-tehnika", "Праска Philips DST8050/80") == "pobut-tehnika"


def test_refine_only_device_categories():
    # не-пристроєву базу (зоо) не чіпає, навіть якщо слово збіглось
    assert refine_category("koty-suhyi-korm", "Корм з кабелем у назві (артефакт)") == "koty-suhyi-korm"
    assert refine_category("inshe", "Навушники") == "inshe"


def test_all_categorize_slugs_are_seeded():
    seeded = {s for s, _ in SEED_CATEGORIES}
    for url in ("koshkam/suhoi-korm", "sobakam/konservi", "koshkam/shampuni", "oshejniki", "igrashki"):
        assert categorize("https://x/" + url) in seeded


def _seeded_slugs():
    """slug-и, реально засіяні міграціями (0001 uncategorized, 0002 зоо, 0007 електроніка)."""
    import glob
    import re
    mig = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
    slugs = set()
    for path in glob.glob(os.path.join(mig, "*.sql")):
        sql = open(path, encoding="utf-8").read()
        if "INSERT INTO category" not in sql:
            continue
        for _name, slug in re.findall(r"\('([^']+)',\s*'([^']+)'\)", sql):
            slugs.add(slug)
    return slugs


def test_catalog_meta_slugs_are_seeded():
    """CATEGORY_UI не має посилатись на категорію, якої нема в міграціях —
    інакше плитка каталогу просто ніколи не зʼявиться."""
    from taxonomy import CATEGORY_UI
    missing = sorted(set(CATEGORY_UI) - _seeded_slugs())
    assert not missing, f"у CATEGORY_UI є незасіяні slug-и: {missing}"


def test_listing_categories_are_known():
    """Кожна категорія, якою тегнуто лістинг у HTML_SOURCES, мусить бути і засіяна
    міграцією, і мати метадані каталогу (розділ+іконку). Ловить друкарську помилку
    в slug: без цього товари тихо падали б у «Інше»."""
    from api.ingest import HTML_SOURCES, URL_CATEGORY
    from taxonomy import CATEGORY_UI
    seeded = _seeded_slugs()
    used = set(URL_CATEGORY.values())
    # джерело-рівневі дефолти (hub, напр. Allo) — теж категорії
    used |= {cfg["category"] for cfg in HTML_SOURCES.values() if cfg.get("category")}
    assert used, "жоден лістинг не тегнуто категорією"
    assert not (used - seeded), f"не засіяні міграцією: {sorted(used - seeded)}"
    assert not (used - set(CATEGORY_UI)), f"без розділу/іконки: {sorted(used - set(CATEGORY_UI))}"


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
