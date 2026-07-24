"""_nice_kop — «гарні» цінові межі для фільтра категорії (§17-nav). Без БД.

Запуск:  python tests/test_nice_kop.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.db import _nice_kop  # noqa: E402


def test_rounds_to_nice_hryvnias():
    assert _nice_kop(2_149_900) == 2_000_000      # 21 499 грн → 20 000
    assert _nice_kop(43_700) == 50_000            # 437 грн → 500
    assert _nice_kop(9_900) == 10_000             # 99 грн → 100
    assert _nice_kop(64_050) == 70_000            # 640.50 грн → 700
    assert _nice_kop(159_00) == 150_00            # 159 грн → 150 (крок 1.5)


def test_extremes_do_not_break():
    assert _nice_kop(1) == 100                    # <1 грн → підлога 1 грн
    assert _nice_kop(99_999_900) == 100_000_000   # ~1 млн грн → 1 000 000


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
