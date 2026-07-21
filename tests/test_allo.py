"""Golden-тест адаптера Allo на ОБРІЗАНИХ касетах (§8.8): хаб-discovery + екстракція.

Запуск:  python tests/test_allo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.allo import AlloAdapter, HUB          # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _read(name):
    with open(os.path.join(CAS, name), encoding="utf-8") as f:
        return f.read()


def _items():
    return AlloAdapter().extract(_read("allo_action.html"))


# ---- discovery: хаб → лендинги ----

def test_discover_actions():
    urls = AlloAdapter().discover(_read("allo_hub.html"))
    assert len(urls) == 9, len(urls)
    assert all(u.startswith("https://allo.ua/ua/events-and-discounts/") and u.endswith("-action/")
               for u in urls)
    assert len(set(urls)) == len(urls)          # без дублів


def test_hub_constant_is_events_page():
    assert HUB == "https://allo.ua/ua/events-and-discounts/"


# ---- екстракція лендингу ----

def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_kopecks_exact_xiaomi_note15pro():
    i = next(x for x in _items() if "note-15-pro" in x.external_ref)
    assert i.price_now_kop == 1399900          # 13 999 ₴ — «сирі» тисячі з пробілом
    assert i.price_old_kop == 1499900          # 14 999 ₴
    assert i.discount_pct == 7
    assert i.title == "Xiaomi REDMI Note 15 Pro 8/256GB Black"


def test_kopecks_exact_samsung_a37():
    i = next(x for x in _items() if "samsung-galaxy-a37" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (2069900, 2299900, 10)
    assert "SM-A376BDGGEUC" in i.title          # MPN у назві — ключ майбутнього матчингу


def test_old_above_now_everywhere():
    for i in _items():
        assert i.price_old_kop is None or i.price_old_kop > i.price_now_kop, i


def test_refs_are_paths_urls_absolute():
    """external_ref — шлях (стабільний ключ §4.8); url — абсолютний (клікабельний)."""
    for i in _items():
        assert i.external_ref.startswith("/ua/products/"), i.external_ref
        assert i.url.startswith("https://allo.ua/"), i.url
        assert i.image_url and i.image_url.startswith("http")


def test_junk_old_price_dropped():
    """«Стара» ціна ≤ поточної — сміття, не знижка: адаптер віддає old=None."""
    fake = """<html><body>
    <div class="product-card"><a href="https://allo.ua/ua/products/x/test-item.html">x</a>
      <div class="product-card__title">Тест</div>
      <div class="v-pb"><div class="v-pb__old"><span class="sum">1 000</span></div>
      <div class="v-pb__cur"><span class="sum">1 000</span></div></div>
    </div></body></html>"""
    items = AlloAdapter().extract(fake)
    assert len(items) == 1
    assert items[0].price_old_kop is None and items[0].discount_pct is None


def test_card_without_price_skipped():
    fake = """<html><body>
    <div class="product-card"><a href="https://allo.ua/ua/products/x/no-price.html">x</a>
      <div class="product-card__title">Без ціни</div>
    </div></body></html>"""
    assert AlloAdapter().extract(fake) == []


def test_category_listing_tv_parses():
    """Лістинг категорії, а не акційний лендинг: інша форма посилання на товар.

    Регресія 2026-07-21: адаптер вимагав `/ua/products/` у href — і категорія
    телевізорів давала НУЛЬ товарів, бо Allo лінкує їх як `/ua/televizory/<назва>.html`.
    Джерело виглядало справним (задачі ok, збоїв нема), просто нічого не приносило.
    Касета — 3 перші картки з живої сторінки, обрізані щоб не тягти 2.8 МБ у репо.
    """
    items = AlloAdapter().extract(_read("allo_tv_listing.html"))
    assert len(items) == 3, len(items)
    assert all("/ua/televizory/" in i.url for i in items), [i.url for i in items]
    assert all(i.title.startswith("Телевізор") for i in items), [i.title for i in items]
    # ціни — цілі копійки (інваріант A), не float
    assert all(isinstance(i.price_now_kop, int) and i.price_now_kop > 0 for i in items)
    assert items[0].price_now_kop == 1699900, items[0].price_now_kop


def test_listing_and_landing_share_one_adapter():
    """Розширення селектора не зламало акційні лендинги — обидві форми живі."""
    assert len(_items()) > 0
    assert len(AlloAdapter().extract(_read("allo_tv_listing.html"))) > 0


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
