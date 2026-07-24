"""Юніт-тести S12 — характеристики з карток (parse_card + clean_attrs).

Касети — РЕАЛЬНІ спец-блоки карток (знято 2026-07-24), обрізані до таблиць фактів
(описи-тексти зрізано ще при знятті — інваріант B5).

Запуск:  python tests/test_cardspec.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.allo import AlloAdapter                       # noqa: E402
from adapters.base import _MAX_ATTRS, clean_attrs           # noqa: E402
from adapters.rozetka import RozetkaAdapter                 # noqa: E402

_CASSETTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cassettes")


def _cassette(name: str) -> str:
    with open(os.path.join(_CASSETTES, name), encoding="utf-8") as f:
        return f.read()


def test_allo_card_golden():
    attrs = AlloAdapter().parse_card(_cassette("allo_card.html"))
    assert len(attrs) == 29, len(attrs)
    assert attrs[0] == ("Тип витяжки", "Телескопічна")
    assert ("Ширина, см", "60 см") in attrs
    # заголовки груп (thead) — не пари
    names = [n for n, _ in attrs]
    assert "Основні" not in names and "Загальні" not in names


def test_rozetka_card_golden():
    attrs = RozetkaAdapter().parse_card(_cassette("rozetka_card.html"))
    assert len(attrs) == 33, len(attrs)
    assert attrs[0] == ("Діагональ екрана", '32"')
    # кілька li у значенні → з'єднання комою
    assert ("Діапазони цифрового тюнера", "DVB-C, DVB-S, DVB-S2, DVB-T, DVB-T2") in attrs


def test_card_parsers_return_zero_on_listing():
    """Лістинг (не картка) → 0 пар: «тихий нуль» у main.py має що ловити."""
    listing = _cassette("allo_tv_listing.html")
    assert AlloAdapter().parse_card(listing) == []
    assert RozetkaAdapter().parse_card(listing) == []


def test_clean_attrs_drops_long_value_entirely():
    """Задовге значення = опис-текст → відкидається ЦІЛКОМ (не трункейт): обрізаний
    опис — усе ще шматок опису, а описи не зберігаємо ані байта (B5)."""
    out = clean_attrs([("Опис", "х" * 301), ("Діагональ", '43"')])
    assert out == [("Діагональ", '43"')]


def test_clean_attrs_dedup_and_whitespace():
    out = clean_attrs([("  Тип   витяжки ", " Телескопічна "),
                       ("тип витяжки", "інше (мобільний дубль блока)")])
    assert out == [("Тип витяжки", "Телескопічна")]


def test_clean_attrs_caps_count():
    out = clean_attrs([(f"Атрибут {i}", "v") for i in range(200)])
    assert len(out) == _MAX_ATTRS


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
