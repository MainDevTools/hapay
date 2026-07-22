"""Golden-тест адаптера add.ua (Аптека Доброго Дня) — ДВОФАЗНИЙ, на двох касетах (§8.8).

add.ua віддає штрихкод лише на сторінці ТОВАРУ, не в лістингу, тож адаптер має дві дії:
  discover(лістинг)     → URL товарів (ItemList ld+json);
  extract(товар)        → один товар зі сторінки, штрихкод із рядка «Штрих-код».

Головне, що стережемо: штрихкод беремо з ТАБЛИЦІ характеристик, а НЕ з ld+json `gtin13`
(там внутрішній SKU крамниці, не EAN). Касета товару має обидва — тест доводить, що
беремо правильний.

Запуск:  python tests/test_addua.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.addua import AdduaAdapter                     # noqa: E402
from matching import pick_gtin                               # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _cas(name):
    with open(os.path.join(CAS, name), encoding="utf-8") as f:
        return f.read()


def test_discover_returns_product_urls():
    urls = AdduaAdapter().discover(_cas("addua_listing.html"))
    assert len(urls) == 3, urls
    assert all(u.startswith("https://www.add.ua/") and u.endswith(".html") for u in urls), urls


def test_extract_one_product_from_page():
    items = AdduaAdapter().extract(_cas("addua_product.html"))
    assert len(items) == 1, items
    i = items[0]
    assert i.title == "Healix (Хелікс) Омега-3 1000 мкг капсули №60", i.title
    assert i.price_now_kop == 73800, i.price_now_kop     # 738,00 ₴ → копійки
    assert i.in_stock is True


def test_barcode_from_table_not_ld_sku():
    """Штрихкод — з рядка «Штрих-код» (4820274801259), НЕ з ld+json gtin13 (=822072, SKU).
    Якби брали ld, ключ був би сміттям і зіставлявся б хибно."""
    i = AdduaAdapter().extract(_cas("addua_product.html"))[0]
    assert i.gtins == ("4820274801259",), i.gtins
    assert pick_gtin(i.gtins) == "04820274801259"
    assert pick_gtin(i.gtins) != pick_gtin(("822072",))   # не внутрішній SKU


def test_ref_from_canonical_path():
    """external_ref — шлях canonical (адаптер отримує лише HTML, не URL сторінки)."""
    i = AdduaAdapter().extract(_cas("addua_product.html"))[0]
    assert i.external_ref == "/ua/healix-heliks-omega-3-1000-mkg-kapsuly-90.html", i.external_ref


def test_image_pointer_only():
    i = AdduaAdapter().extract(_cas("addua_product.html"))[0]
    assert i.image_url and i.image_url.startswith("https://"), i.image_url
    assert not i.image_url.startswith("data:")


def test_discover_re_distinguishes_listing_from_product():
    """Регекс маршрутизації: лістинг `/ua/<cat>/` → discover, товар `/ua/<slug>.html` → extract."""
    import re
    from api.ingest import HTML_SOURCES
    dre = HTML_SOURCES["AddUa"]["discover_re"]
    assert re.search(dre, "https://www.add.ua/ua/kosmetika/")            # лістинг
    assert not re.search(dre, "https://www.add.ua/ua/healix-omega-90.html")  # товар


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
