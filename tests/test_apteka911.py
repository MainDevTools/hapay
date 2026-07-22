"""Golden-тест адаптера apteka911 (Аптека 911) — ДВОФАЗНИЙ, на двох касетах (§8.8).

apteka911 віддає штрихкод лише на сторінці ТОВАРУ (у `<title>` в дужках), не в лістингу,
тож адаптер має дві дії:
  discover(лістинг) → URL товарів (<a href> з патерном `-p<id>`);
  extract(товар)    → один товар зі сторінки.

Три речі, які тут стережемо (кожна — реальний факт, заміряний 2026-07-22):
  1. ШТРИХКОД — з `<title>` у дужках, і саме 8–14-цифровий: у назві є й інші дужки
     («(Ля Рош-Позе)», «(Франція)», обсяг «(40 мл)») — беремо лише числовий блок.
  2. ЦІНА — з DOM `.price-new`, бо ld+json Offer.price = null (якби брали з ld, ціни не
     було б зовсім). Касета навмисне має price:null у ld та 734.00 у DOM.
  3. КОНТРОЛЬНИЙ СИМВОЛ у ld+json: apteka911 кладе сирий перенос рядка в опис товару, і
     строгий json.loads на ньому падає — тоді Product-блок губився б, а з ним увесь товар.
     Касета відтворює це (опис у два рядки); тест доводить, що адаптер (strict=False) вистоює.

Касети — дистилят живих сторінок La Roche (не повний HTML: без 400 КБ чужого маркетингу),
із РЕАЛЬНИМИ значеннями. Ціль — Toleriane, штрихкод 3337875578486: він є і в Podorozhnyk,
і в AddUa, тож apteka911 робить його ТРИкрамничною групою.

Запуск:  python tests/test_apteka911.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.apteka911 import Apteka911Adapter                # noqa: E402
from matching import pick_gtin                                  # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _cas(name):
    with open(os.path.join(CAS, name), encoding="utf-8") as f:
        return f.read()


def test_discover_returns_product_urls():
    """Лістинг → URL товарів; дедуп (фото+назва — два лінки на товар), бренд/категорія — геть."""
    urls = Apteka911Adapter().discover(_cas("apteka911_listing.html"))
    assert len(urls) == 3, urls                                 # 3 унікальні, дубль злився
    import re
    assert all(u.startswith("https://apteka911.ua/ua/shop/") for u in urls), urls
    assert all(re.search(r"-p\d+$", u) for u in urls), urls     # усі — товари
    assert len(set(urls)) == len(urls), "дедуп не спрацював"


def test_extract_one_product_from_page():
    items = Apteka911Adapter().extract(_cas("apteka911_product.html"))
    assert len(items) == 1, items
    i = items[0]
    assert i.title.startswith("Крем для обличчя La Roche-Posay"), i.title
    assert i.price_now_kop == 73400, i.price_now_kop            # 734.00 грн → копійки
    assert i.in_stock is True


def test_barcode_from_title_8_to_14_digits():
    """Штрихкод — числовий блок у дужках title (3337875578486), НЕ «(Ля Рош-Позе)»/«(Франція)».
    Цей EAN є і в Podorozhnyk, і в AddUa → apteka911 робить групу трикрамничною."""
    i = Apteka911Adapter().extract(_cas("apteka911_product.html"))[0]
    assert i.gtins == ("3337875578486",), i.gtins
    assert pick_gtin(i.gtins) == "03337875578486"               # канонічний GTIN-14 = ключ у БД


def test_price_from_dom_not_ldjson():
    """Ціна — з DOM `.price-new`, а НЕ з ld+json (там Offer.price=null). Якби брали з ld,
    товар випав би (без ціни). 73400 доводить, що читаємо DOM."""
    i = Apteka911Adapter().extract(_cas("apteka911_product.html"))[0]
    assert i.price_now_kop == 73400, i.price_now_kop


def test_control_char_in_ldjson_tolerated():
    """РЕГРЕС: ld+json Product apteka911 має сирий контрольний символ (перенос) в описі.
    Строгий json.loads на ньому падає → Product губиться → extract() поверне []. strict=False
    рятує. Касета відтворює баг; порожній результат тут = регрес адаптера."""
    items = Apteka911Adapter().extract(_cas("apteka911_product.html"))
    assert len(items) == 1, "контрольний символ у ld+json з'їв товар — strict=False зламано"


def test_ref_from_canonical_path():
    """external_ref — шлях canonical (адаптер отримує лише HTML, не URL сторінки)."""
    i = Apteka911Adapter().extract(_cas("apteka911_product.html"))[0]
    assert i.external_ref.endswith("-p65091"), i.external_ref
    assert i.external_ref.startswith("/ua/shop/"), i.external_ref


def test_image_pointer_only():
    i = Apteka911Adapter().extract(_cas("apteka911_product.html"))[0]
    assert i.image_url and i.image_url.startswith("https://"), i.image_url
    assert not i.image_url.startswith("data:")


def test_discover_re_distinguishes_listing_from_product():
    """Регекс маршрутизації: лістинг (бренд/категорія/page) → discover, товар `-p<id>` → extract."""
    import re
    from api.ingest import HTML_SOURCES
    dre = HTML_SOURCES["Apteka911"]["discover_re"]
    assert re.search(dre, "https://apteka911.ua/ua/shop/brands/la-roche")        # лістинг
    assert re.search(dre, "https://apteka911.ua/ua/shop/brands/la-roche/page=2")  # пагінація
    assert not re.search(dre, "https://apteka911.ua/ua/shop/krem-...-p65091")     # товар


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
