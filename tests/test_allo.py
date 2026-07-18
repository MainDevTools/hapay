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
