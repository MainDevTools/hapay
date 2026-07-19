"""Golden-тест адаптера Brain на ОБРІЗАНІЙ касеті ВІДРЕНДЕРЕНОГО (WebView) лістингу (§8.8).

Brain — SPA: ціни лише після JS → збирається у webview-режимі. Дані з data-атрибутів.

Запуск:  python tests/test_brain.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.brain import BrainAdapter                 # noqa: E402
from matching import extract_mpn                         # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "brain_listing.html"), encoding="utf-8") as f:
        return BrainAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_data_attr_price_and_discount():
    """Ціни з data-price/data-without-discount-price (не з «брудних» спанів розстрочки)."""
    i = next(x for x in _items() if "xiaomi" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop, i.discount_pct) == (1399900, 1499900, 7)


def test_no_discount_when_without_price_zero():
    """data-without-discount-price='0' → не знижка (Samsung A07)."""
    i = next(x for x in _items() if "samsung_galaxy_a07" in x.external_ref)
    assert i.price_now_kop == 549900
    assert i.price_old_kop is None and i.discount_pct is None
    # той самий A07, що в Moyo/Rozetka/Citrus (SM-A075FZKGSEK) → крос-крамнична група T15
    assert extract_mpn(i.title) == "SM-A075FZKGSEK"


def test_sku_in_parens_is_not_mpn():
    """Xiaomi має внутрішній SKU (1183684) у дужках — самі цифри, НЕ артикул → mpn=None."""
    i = next(x for x in _items() if "xiaomi" in x.external_ref)
    assert extract_mpn(i.title) is None


def test_image_from_lazy_data_observe_src():
    for i in _items():
        assert i.image_url and i.image_url.startswith("https://brain.com.ua/"), i.image_url


def test_refs_paths_urls_absolute():
    for i in _items():
        assert i.external_ref.startswith("/ukr/") and "-p" in i.external_ref, i.external_ref
        assert i.url.startswith("https://brain.com.ua/"), i.url


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
