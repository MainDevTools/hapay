"""Golden-тест адаптера Citrus на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Особливість: хешовані CSS-класи (Next.js) → перевіряємо, що ПРЕФІКСНІ селектори й
стабільний .old-price ловлять ціни, і що Next-проксі фото декодовано в пряму CDN.

Запуск:  python tests/test_citrus.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.citrus import CitrusAdapter               # noqa: E402
from matching import extract_mpn                         # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "citrus_listing.html"), encoding="utf-8") as f:
        return CitrusAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_kopecks_exact_samsung_s26():
    i = next(x for x in _items() if "s948b-zkg" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (6529900, 7099900, 8)
    # той самий S26 Ultra Black, що в Comfy (SM-S948BZKGEUC) → крос-крамнична група T15
    assert extract_mpn(i.title) == "SM-S948BZKGEUC"


def test_kopecks_exact_iphone():
    i = next(x for x in _items() if "iphone-17-pro" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (5999900, 6699900, 10)


def test_card_without_old_price_is_not_discount():
    i = next(x for x in _items() if x.price_old_kop is None)
    assert i.price_now_kop == 799900 and i.discount_pct is None
    assert extract_mpn(i.title) == "SM-A165FZKBEUC"    # MPN є і без знижки — база матчингу


def test_image_next_proxy_decoded_to_direct_https():
    for i in _items():
        assert i.image_url and i.image_url.startswith("https://") and "/_next/image" not in i.image_url, i.image_url


def test_refs_paths_urls_absolute():
    for i in _items():
        assert i.external_ref.startswith("/smartfony/"), i.external_ref
        assert i.url.startswith("https://www.ctrs.com.ua/"), i.url


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
