"""Golden-тест адаптера Foxtrot на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Запуск:  python tests/test_foxtrot.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.foxtrot import FoxtrotAdapter          # noqa: E402
from matching import extract_mpn                      # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "foxtrot_listing.html"), encoding="utf-8") as f:
        return FoxtrotAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_kopecks_exact_samsung_s26():
    i = next(x for x in _items() if "samsung-sm-s942b" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (4229900, 4599900, 8)
    assert i.in_stock is True


def test_samsung_full_mpn_not_short():
    """Регресія найдовшого збігу: назва має і SM-S942B (лінійка), і (SM-S942BZKGEUC);
    ключем мусить бути ПОВНИЙ артикул — коротка модель спільна для варіантів."""
    i = next(x for x in _items() if "samsung-sm-s942b" in x.external_ref)
    assert extract_mpn(i.title) == "SM-S942BZKGEUC"


def test_kopecks_exact_iphone():
    i = next(x for x in _items() if "apple-iphone-17" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (6199900, 6699900, 7)
    assert extract_mpn(i.title) == "MG8G4AF/A"


def test_card_without_old_price_is_not_discount():
    i = next(x for x in _items() if "xiaomi-redmi-15c" in x.external_ref)
    assert i.price_now_kop == 699900
    assert i.price_old_kop is None and i.discount_pct is None


def test_refs_are_paths_urls_absolute():
    for i in _items():
        assert i.external_ref.startswith("/uk/shop/"), i.external_ref
        assert i.url.startswith("https://www.foxtrot.com.ua/"), i.url
        assert i.image_url and i.image_url.startswith("https://"), i.image_url


def test_title_from_data_attribute():
    for i in _items():
        assert i.title.startswith("Смартфон"), i.title


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
