"""Golden-тест екстрактора PetChoice (miniShop2) на обрізаній касеті (§8.8).

Запуск:  python tests/test_petchoice.py   (потребує selectolax)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.petchoice import PetChoiceAdapter, _split_price_kop  # noqa: E402
from selectolax.parser import HTMLParser                            # noqa: E402

CASSETTE = os.path.join(os.path.dirname(__file__), "cassettes", "petchoice_akcii.html")


def _items():
    with open(CASSETTE, encoding="utf-8") as f:
        return PetChoiceAdapter().extract(f.read())


def _by(items, tail):
    return next(i for i in items if i.external_ref.endswith(tail))


def test_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.url for i in items}) == 2


def test_no_dup_and_now_below_old():
    items = _items()
    assert len({i.external_ref for i in items}) == 3
    for i in items:
        if i.price_old_kop is not None:
            assert i.price_now_kop < i.price_old_kop, i


def test_kopecks_royal_canin_variants():
    items = _items()
    a = _by(items, "#v=3-2-кг-800-гр")
    assert (a.price_now_kop, a.price_old_kop) == (102000, 136000)   # 1020,00 / 1360,00
    assert a.variant_note == "3,2 кг + 800 гр" and a.image_url and "Royal Canin" in a.title
    b = _by(items, "#v=12-3-кг")
    assert (b.price_now_kop, b.price_old_kop) == (294000, 420000)   # 2940,00 / 4200,00


def test_all_refs_per_variant():
    for i in _items():
        assert "#v=" in i.external_ref or "#k=" in i.external_ref


def test_split_price_parser():
    """miniShop2 грн+коп: '1360' + '.small'>00 → 136000."""
    node = HTMLParser('<div class="p">1360<div class="small">00</div></div>').css_first(".p")
    assert _split_price_kop(node) == 136000
    node2 = HTMLParser('<div class="p">2940<div class="small">50</div></div>').css_first(".p")
    assert _split_price_kop(node2) == 294050


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL  {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
