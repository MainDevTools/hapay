"""Логіка сторожа збору — без БД і без мережі.

Тут перевіряється саме те, через що сторожі бувають марні: або шлють на кожній
перевірці (їх вимикають на другий день), або замовкають назавжди після першого
разу (і про добову зупинку ніхто не дізнається).

Запуск:  python -m pytest tests/test_alert.py -q
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.alert_collect import decide  # noqa: E402

T0 = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def test_first_run_healthy_is_quiet():
    """Перший запуск на справній системі не має нікого будити."""
    assert decide(None, True, T0) == ("ok", None)


def test_first_run_broken_alerts():
    """А якщо на першому ж запуску все лежить — сказати треба."""
    assert decide(None, False, T0) == ("down", "down")


def test_transition_to_down_alerts_once():
    prev = {"state": "ok", "last_sent_at": None}
    assert decide(prev, False, T0) == ("down", "down")


def test_still_down_is_silent_until_remind_window():
    """Головне проти спаму: поки вікно не минуло — мовчимо."""
    prev = {"state": "down", "last_sent_at": T0}
    assert decide(prev, False, T0 + timedelta(hours=1)) == ("down", None)
    assert decide(prev, False, T0 + timedelta(hours=5, minutes=59)) == ("down", None)


def test_still_down_reminds_after_window():
    """Але про добову зупинку сторож зобов'язаний нагадати."""
    prev = {"state": "down", "last_sent_at": T0}
    assert decide(prev, False, T0 + timedelta(hours=6)) == ("down", "reminder")
    assert decide(prev, False, T0 + timedelta(hours=25)) == ("down", "reminder")


def test_down_without_sent_at_reminds():
    """Впало, але надіслати не вдалося (канал не налаштований) — не вважаємо
    повідомленим і нагадаємо, щойно канал з'явиться."""
    prev = {"state": "down", "last_sent_at": None}
    assert decide(prev, False, T0 + timedelta(minutes=1)) == ("down", "reminder")


def test_recovery_alerts():
    prev = {"state": "down", "last_sent_at": T0}
    assert decide(prev, True, T0 + timedelta(hours=2)) == ("ok", "recovered")


def test_steady_ok_is_silent():
    prev = {"state": "ok", "last_sent_at": T0}
    assert decide(prev, True, T0 + timedelta(days=3)) == ("ok", None)


def test_remind_window_is_configurable():
    prev = {"state": "down", "last_sent_at": T0}
    assert decide(prev, False, T0 + timedelta(hours=2), remind_hours=1) == ("down", "reminder")
