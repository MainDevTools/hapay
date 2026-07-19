"""Golden-тест адаптера KTC на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Особливість: знижкова ціна крамить стару+поточну в одному .loop__price
(<del>стара</del><div>поточна</div>) → del видаляємо перед читанням поточної.

Запуск:  python tests/test_ktc.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.ktc import KtcAdapter                     # noqa: E402
from matching import extract_mpn                         # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "ktc_listing.html"), encoding="utf-8") as f:
        return KtcAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_del_stripped_promo_price():
    """<del>70 999</del><div>65 299 грн</div> → поточна=65299, стара=70999 (не «злипло»)."""
    i = next(x for x in _items() if "galaxy_s26_ultra" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (6529900, 7099900, 8)
    assert extract_mpn(i.title) == "SM-S948BZKGEUC"    # збіг із Comfy/Citrus/Rozetka


def test_iphone_discount():
    i = next(x for x in _items() if "iphone_16" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (3399900, 4349900, 22)


def test_no_discount_single_price():
    i = next(x for x in _items() if "galaxy_a07" in x.external_ref)
    assert i.price_now_kop == 549900
    assert i.price_old_kop is None and i.discount_pct is None
    assert extract_mpn(i.title) == "SM-A075FZKGSEK"    # збіг із Moyo/Rozetka/Citrus/Brain


def test_refs_paths_urls_absolute():
    for i in _items():
        assert i.external_ref.startswith("/goods/"), i.external_ref
        assert i.url.startswith("https://ktc.ua/"), i.url


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
