"""Golden-тест адаптера Interatletika на ОБРІЗАНІЙ касеті (§8.8): 2 реальні картки.

Стережемо: пробіли-тисячники в ціні («53 370 ₴»), відносні href/src (клеяться до
BASE), обхід 1×1 data:-заглушки (ia--fake-image) на користь ia--real-image,
old=None завжди (крамниця перекреслених цін не показує; селектор невідомий —
НЕ вгадуємо, інваріант чесності).

Запуск:  python -m pytest tests/test_interatletika.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.interatletika import InteratletikaAdapter       # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "interatletika_listing.html"), encoding="utf-8") as f:
        return InteratletikaAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 2, len(items)
    assert len({i.external_ref for i in items}) == 2


def test_price_with_thousands_spaces():
    """«53 370 ₴» → 5 337 000 коп."""
    i = next(x for x in _items() if "toptrack-kd152d" in x.external_ref)
    assert i.price_now_kop == 5337000, i.price_now_kop
    assert i.price_old_kop is None


def test_relative_href_glued_to_base():
    for i in _items():
        assert i.external_ref.startswith("https://shop.interatletika.com/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


def test_image_real_not_fake_placeholder():
    """Перший <img> картки — 1×1 data:-заглушка; беремо ia--real-image."""
    for i in _items():
        assert i.image_url is not None, i.title
        assert i.image_url.startswith("https://shop.interatletika.com/upload/"), i.image_url
        assert not i.image_url.startswith("data:"), i.image_url


def test_title_clean():
    i = _items()[0]
    assert i.title == "Бігова доріжка TopTrack KD152D-A", i.title


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
