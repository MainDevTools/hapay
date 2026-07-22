"""Тести розширення пошуку (§9.1) — чисті, без БД.

Головне: українець набирає бренд кирилицею фонетично, а в назвах він латиницею.
Перевіряємо, що патерни містять і оригінал, і латинську форму, і що решта запиту
зберігається («айфон 15» → «iphone 15»).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from search import search_patterns          # noqa: E402


def _has(q, needle):
    """Чи є серед патернів такий, що містить needle (без %-обгортки)."""
    return any(needle in p.strip("%") for p in search_patterns(q))


def test_cyrillic_brand_maps_to_latin():
    assert _has("айфон", "iphone")
    assert _has("самсунг", "samsung")
    assert _has("ксіомі", "xiaomi")


def test_keeps_rest_of_query():
    """«айфон 15» → серед патернів «iphone 15» (бренд підставлено, число збережено)."""
    assert _has("айфон 15", "iphone 15")
    assert _has("самсунг galaxy", "samsung galaxy")


def test_multiword_brand():
    """Фразовий бренд «ля рош» → «la roche» (не порізати на слова)."""
    assert _has("ля рош", "la roche")
    assert _has("лярош", "la roche")


def test_original_always_present():
    """Розширення ДОДАЄ, не замінює: оригінал завжди серед патернів (недозлиття безпечне)."""
    pats = search_patterns("айфон")
    assert "%айфон%" in pats
    assert "%iphone%" in pats


def test_latin_query_unchanged():
    """Латинський запит нічого не ламає — просто повертається як є."""
    assert search_patterns("iphone 15") == ["%iphone 15%"]


def test_whitespace_normalized():
    assert search_patterns("  Samsung   Galaxy  ") == ["%samsung galaxy%"]


def test_empty_query():
    assert search_patterns("") == []
    assert search_patterns(None) == []
    assert search_patterns("   ") == []


def test_pharmacy_brand():
    """Аптечна дермокосметика: «віші» → vichy, «серове» → cerave."""
    assert _has("віші", "vichy")
    assert _has("серове", "cerave")


def _main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v) and getattr(v, "__module__", None) == __name__]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
