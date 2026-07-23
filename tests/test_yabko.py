"""Golden-тест адаптера Yabko на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Головна пастка — ВАЛЮТА: span.old у картці містить ціну В ДОЛАРАХ («432$» —
двовалютний показ Yabko), не перекреслену стару. Взяти її як price_old means
«знижка» з курсу долара. Адаптер мусить давати old=None завжди; current у грн
із nbsp-сутностями («19 399&nbsp;грн»).

Запуск:  python -m pytest tests/test_yabko.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.yabko import YabkoAdapter                       # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "yabko_listing.html"), encoding="utf-8") as f:
        return YabkoAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_dollar_old_never_leaks():
    """«432$» НЕ стає ані old, ані now."""
    for i in _items():
        assert i.price_old_kop is None, (i.title, i.price_old_kop)
        assert i.price_now_kop > 100000, (i.title, i.price_now_kop)   # 432$≈43200 коп відсіклось би тут


def test_current_uah_with_nbsp():
    i = next(x for x in _items() if "hero-13" in x.external_ref)
    assert i.price_now_kop == 1939900, i.price_now_kop
    assert i.title == "Екшн-камера GoPro Hero 13 Black (CHDHX-131-RW) (Standard)", i.title


def test_ref_canonical():
    for i in _items():
        assert i.external_ref.startswith("https://jabko.ua/"), i.external_ref
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
