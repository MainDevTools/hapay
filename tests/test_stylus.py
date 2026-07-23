"""Golden-тест адаптера Stylus на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Три речі, які тут стережемо (кожна вже стрелила на розвідці 2026-07-23):
1. nbsp-сутності: ціни в DOM — «9&nbsp;959&nbsp;грн»; без розгортання сутності
   [\\d\\s]-клас цін не бачить і адаптер мовчки віддає нуль позицій.
2. Лічильник відгуків стоїть у DOM перед старою ціною: склейка тексту дає
   «19 959 грн» замість «9 959 грн» — тому regex якорений на початок вузла («>»).
   Мінімальна (поточна) ціна при цьому НЕушкоджена — ламалась лише old, тож
   LD-звірка поточних цін дефект маскувала.
3. Назва — з img[title] (чиста); img[alt] несе хвіст характеристик.

Запуск:  python -m pytest tests/test_stylus.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.stylus import StylusAdapter                     # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "stylus_listing.html"), encoding="utf-8") as f:
        return StylusAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_nbsp_prices_not_lost_and_counter_not_glued():
    """Пастки 1+2 разом: nbsp розгорнуто, лічильник відгуків НЕ приклеївся до old."""
    i = next(x for x in _items() if "xiaomi-redmi-note-15" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (829900, 995900), (i.price_now_kop, i.price_old_kop)


def test_now_is_min_old_is_max():
    for i in _items():
        assert i.price_old_kop is None or i.price_old_kop > i.price_now_kop, \
            (i.title, i.price_now_kop, i.price_old_kop)


def test_title_clean_without_specs_tail():
    """Назва з img[title] — без хвоста характеристик із alt («…: Дисплей…»)."""
    i = next(x for x in _items() if "xiaomi-redmi-note-15" in x.external_ref)
    assert i.title == "Смартфон Xiaomi Redmi Note 15 6/128GB Black (Global, NFC)", i.title
    assert "Дисплей" not in i.title


def test_ref_canonical_on_stylus_domain():
    """URL — на stylus.ua (НЕ на stls.store, як у LD offers)."""
    for i in _items():
        assert i.external_ref.startswith("https://stylus.ua/uk/"), i.external_ref
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
