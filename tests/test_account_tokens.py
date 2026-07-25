"""S13 — коди verify/reset: генерація, хешування, email LogSender. Без БД/мережі.

Запуск:  python tests/test_account_tokens.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import auth as qauth  # noqa: E402
from api import email as qemail  # noqa: E402


def test_code_is_six_digits():
    for _ in range(50):
        c = qauth.make_code()
        assert len(c) == 6 and c.isdigit(), c


def test_hash_stable_and_distinct():
    assert qauth.hash_code("123456") == qauth.hash_code("123456")   # детерміновано
    assert qauth.hash_code("123456") != qauth.hash_code("123457")   # різні коди — різні хеші
    assert len(qauth.hash_code("000000")) == 64                     # sha256 hex


def test_ttls_sane():
    assert qauth.VERIFY_TTL_S == 24 * 3600
    assert qauth.RESET_TTL_S == 3600
    assert qauth.RESET_TTL_S < qauth.VERIFY_TTL_S       # reset чутливіший → коротший


def test_email_logsender_never_raises_without_smtp(capsys=None):
    # без SMTP_HOST send повертає False (LogSender) і НЕ кидає
    old = os.environ.pop("SMTP_HOST", None)
    try:
        assert qemail.send("x@y.z", "тема", "тіло") is False
    finally:
        if old is not None:
            os.environ["SMTP_HOST"] = old


def test_email_bodies_contain_code():
    subj, body = qemail.verify_body("424242")
    assert "424242" in body and "Хапай" in subj
    subj2, body2 = qemail.reset_body("135790")
    assert "135790" in body2 and "парол" in subj2.lower()   # «пароля» — корінь, не форма


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
