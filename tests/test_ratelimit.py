"""RateLimiter — sliding-window per-IP (bug-review 2026-07-25). Без БД/мережі.

Запуск:  python tests/test_ratelimit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.ratelimit import RateLimiter  # noqa: E402


def test_allows_up_to_limit_then_blocks():
    rl = RateLimiter()
    # 3 спроби / вікно 100с; час інжектуємо
    for i in range(3):
        ok, _ = rl.check("1.2.3.4", 3, 100, now=1000.0 + i)
        assert ok, f"спроба {i} мала пройти"
    ok, retry = rl.check("1.2.3.4", 3, 100, now=1003.0)
    assert not ok and retry > 0, "4-та понад ліміт → блок із Retry-After"


def test_window_slides():
    rl = RateLimiter()
    for i in range(3):
        rl.check("ip", 3, 100, now=1000.0 + i)
    assert not rl.check("ip", 3, 100, now=1050.0)[0]      # ще в вікні
    # найстаріша (t=1000) випала з вікна [1101-100=1001 .. ] → одна вільна комірка
    assert rl.check("ip", 3, 100, now=1101.0)[0]


def test_keys_independent():
    rl = RateLimiter()
    for _ in range(3):
        rl.check("a", 3, 100, now=1000.0)
    assert not rl.check("a", 3, 100, now=1000.0)[0]
    assert rl.check("b", 3, 100, now=1000.0)[0]           # інший IP — свій бюджет


def test_rejected_attempts_do_not_extend_block():
    """Відхилені спроби НЕ реєструються — інакше зловмисник тримав би вікно повним
    вічно. Після проходу вікна доступ відновлюється попри спам у блокований період."""
    rl = RateLimiter()
    for _ in range(3):
        rl.check("ip", 3, 100, now=1000.0)
    for t in range(1001, 1099):                            # спам під час блоку
        assert not rl.check("ip", 3, 100, now=float(t))[0]
    # усі 3 зареєстровані на t=1000 → вікно чисте після 1100
    assert rl.check("ip", 3, 100, now=1101.0)[0]


def test_sweep_frees_stale_keys():
    rl = RateLimiter()
    rl.check("old", 5, 100, now=1000.0)
    # наступна дія через понад годину + інший ключ → sweep прибирає 'old'
    rl.check("new", 5, 100, now=1000.0 + 3700)
    assert "old" not in rl._hits, "застарілий ключ мав бути прибраний sweep-ом"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
