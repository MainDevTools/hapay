"""Golden-тест сигнальної логіки probe.analyze() на синтетичній фікстурі.

Запуск без залежностей:  python tests/test_probe.py
Або через pytest:        pytest tests/test_probe.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import probe  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_listing.html")


def _analyze_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        html = f.read()
    return probe.analyze(html, product_re=r'href="(/[^"]*?-\d+(?:\.html)?/?)"')


def test_finds_two_discounted_cards():
    """2 знижені картки (line-through + product-price-old), незнижена не рахується."""
    r = _analyze_fixture()
    assert r["old_price"] == 2, r["old_price"]


def test_finds_discount_percents():
    r = _analyze_fixture()
    assert r["discount_pct"] == 2, r["discount_pct"]  # -15% і -25%


def test_detects_jsonld():
    r = _analyze_fixture()
    assert r["jsonld"] == 1, r["jsonld"]


def test_not_blocked_on_clean_page():
    r = _analyze_fixture()
    assert r["blocked"] is False
    assert r["antibot"] is None


def test_has_current_price_signal():
    r = _analyze_fixture()
    assert r["curr_price"] > 0, r["curr_price"]


def test_extracts_unique_product_refs():
    """3 різні товарні URL → 3 унікальні external_ref (канонізовані)."""
    r = _analyze_fixture()
    assert r["uniq_items"] == 3, (r["uniq_items"], r["sample_refs"])


def test_canon_ref_strips_query_and_slash():
    assert probe.canon_ref("/ua/shop/Korm-1234/?utm=x#frag") == "/ua/shop/korm-1234"


def test_block_marker_detected():
    """Сильний CF-маркер → blocked; порожня чиста сторінка → ні."""
    blocked = probe.analyze("<html><body>Just a moment...</body></html>", None)
    assert blocked["blocked"] is True and blocked["antibot"] == "blocked"


def test_challenge_platform_alone_is_not_block():
    """Голий challenge-platform-скрипт на контентній сторінці ≠ блок (урок PetChoice)."""
    html = ('<html><body>' + 'x' * 70000 +
            '<div class="product-price-old">100,00</div>'
            '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
            '</body></html>')
    r = probe.analyze(html, None)
    assert r["cf"] is True
    assert r["blocked"] is False
    assert r["antibot"] is None


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}  -> {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
