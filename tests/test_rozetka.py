"""Golden-тест адаптера Rozetka на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Запуск:  python tests/test_rozetka.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.rozetka import RozetkaAdapter             # noqa: E402
from matching import extract_mpn                        # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "rozetka_listing.html"), encoding="utf-8") as f:
        return RozetkaAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_kopecks_exact_samsung_s26():
    i = next(x for x in _items() if "sm-s942bzkgeuc" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (4229900, 4599900, 8)
    # той самий S26, що у Foxtrot (SM-S942BZKGEUC, 42299/45999) → крос-крамнична група T15
    assert extract_mpn(i.title) == "SM-S942BZKGEUC"


def test_kopecks_exact_iphone():
    i = next(x for x in _items() if "iphone-17-pro" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (5999900, 6699900, 10)
    assert extract_mpn(i.title) == "MG8H4AF/A"


def test_card_without_old_price_is_not_discount():
    i = next(x for x in _items() if x.price_old_kop is None)
    assert i.price_now_kop == 899900 and i.discount_pct is None


def test_refs_paths_urls_absolute_img_https():
    for i in _items():
        assert i.external_ref.startswith("/ua/") and "/p" in i.external_ref, i.external_ref
        assert i.url.startswith("https://rozetka.com.ua/"), i.url
        assert i.image_url and i.image_url.startswith("https://"), i.image_url


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
