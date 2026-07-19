"""Golden-тест адаптера Moyo на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Запуск:  python tests/test_moyo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.moyo import MoyoAdapter                # noqa: E402
from matching import extract_mpn                      # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "moyo_listing.html"), encoding="utf-8") as f:
        return MoyoAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_kopecks_exact_samsung_a37():
    i = next(x for x in _items() if "galaxy_a37" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (1709900, 1899900, 10)
    assert extract_mpn(i.title) == "SM-A376BZABEUC"


def test_kopecks_exact_iphone_17_pro_max():
    i = next(x for x in _items() if "iphone_17_pro_max" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (6699900, 7299900, 8)
    assert extract_mpn(i.title) == "MFYM4AF/A"


def test_card_without_old_price_is_not_discount():
    i = next(x for x in _items() if "galaxy_a07" in x.external_ref)
    assert i.price_now_kop == 549900
    assert i.price_old_kop is None and i.discount_pct is None
    assert extract_mpn(i.title) == "SM-A075FZKGSEK"   # MPN є і без знижки — база матчингу


def test_image_from_base64_pointer():
    """Фото ховається в base64 data-srcset-hash → мусить розгорнутись у https-вказівник."""
    for i in _items():
        assert i.image_url and i.image_url.startswith("https://"), i.image_url


def test_refs_are_paths_urls_absolute():
    for i in _items():
        assert i.external_ref.startswith("/ua/"), i.external_ref
        assert i.url.startswith("https://www.moyo.ua/"), i.url


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
