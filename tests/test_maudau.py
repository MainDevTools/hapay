"""Golden-тест адаптера MAUDAU на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Гачки — data-testid (Tailwind-класи хешовано-непридатні): productItem корінь,
productName назва (з SKU в дужках), finalPrice поточна, productFullPrice стара
(line-through). Стережемо пробіл-тисячники й канонічні /product/-URL.

Запуск:  python -m pytest tests/test_maudau.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.maudau import MaudauAdapter                     # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "maudau_listing.html"), encoding="utf-8") as f:
        return MaudauAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_discount_pair_from_testids():
    """finalPrice «18 445 ₴» + productFullPrice «21 700 ₴» → 1844500/2170000."""
    i = next(x for x in _items() if "koliaska-balios" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (1844500, 2170000), (i.price_now_kop, i.price_old_kop)


def test_plain_card_no_old():
    i = next(x for x in _items() if "velano" in x.external_ref)
    assert i.price_old_kop is None
    assert i.price_now_kop == 277900, i.price_now_kop


def test_title_with_sku_parens():
    """Назва з productName; SKU в дужках лишаємо — він годує матчер."""
    i = next(x for x in _items() if "velano" in x.external_ref)
    assert i.title == "Прогулянкова коляска VELANO Jett Light green (47313)", i.title


def test_ref_canonical():
    for i in _items():
        assert i.external_ref.startswith("https://maudau.com.ua/product/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


def test_image_pointer_only():
    for i in _items():
        if i.image_url is not None:
            assert i.image_url.startswith("http"), i.image_url


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
