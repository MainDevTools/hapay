"""Golden-тест адаптера Comfy на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Запуск:  python tests/test_comfy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.comfy import ComfyAdapter                # noqa: E402
from matching import extract_mpn                        # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "comfy_listing.html"), encoding="utf-8") as f:
        return ComfyAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_kopecks_exact_samsung_a37():
    i = next(x for x in _items() if "galaxy-a37" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (2069900, 2299900, 10)
    # той самий A37 Lavender, що в Allo → крос-крамнична група T15
    assert extract_mpn(i.title) == "SM-A376BLVGEUC"


def test_kopecks_exact_iphone():
    i = next(x for x in _items() if "iphone-17-pro-max" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (6699900, 7299900, 8)


def test_card_without_old_price_is_not_discount():
    i = next(x for x in _items() if "redmi-note-15" in x.external_ref)
    assert i.price_now_kop == 1399900
    assert i.price_old_kop is None and i.discount_pct is None


def test_refs_paths_urls_absolute_img_https():
    for i in _items():
        assert i.external_ref.startswith("/smartfon-"), i.external_ref
        assert i.url.startswith("https://comfy.ua/"), i.url
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
