"""Тести auth (S11) — паролі + JWT (чисті, без БД).

Доводить: пароль не відновити зі сховища, невірний пароль відсіюється, токен із
підробленим підписом / протермінований / без секрета — не проходить.

Запуск:  python tests/test_auth.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import auth  # noqa: E402


# ── паролі ────────────────────────────────────────────────────────────────────

def test_hash_roundtrip():
    h = auth.hash_password("correct horse battery")
    assert auth.verify_password("correct horse battery", h)


def test_wrong_password_rejected():
    h = auth.hash_password("s3cret-pass")
    assert not auth.verify_password("s3cret-pazz", h)
    assert not auth.verify_password("", h)


def test_hash_is_not_plaintext_and_salted():
    h1 = auth.hash_password("same")
    h2 = auth.hash_password("same")
    assert "same" not in h1
    assert h1 != h2                       # унікальна сіль → різні хеші того самого пароля
    assert h1.startswith("pbkdf2_sha256$")


def test_verify_tolerates_garbage_stored():
    for bad in ("", "not-a-hash", "a$b$c"):
        assert auth.verify_password("x", bad) is False


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_token_roundtrip():
    os.environ["JWT_SECRET"] = "test-secret-at-least-16-chars-long"
    t = auth.make_token(42, "collector")
    claims = auth.verify_token(t)
    assert claims["sub"] == 42 and claims["role"] == "collector"


def test_tampered_signature_rejected():
    os.environ["JWT_SECRET"] = "test-secret-at-least-16-chars-long"
    t = auth.make_token(1, "user")
    tampered = t[:-4] + ("aaaa" if not t.endswith("aaaa") else "bbbb")
    try:
        auth.verify_token(tampered)
        raise AssertionError("мала бути AuthError")
    except auth.AuthError:
        pass


def test_payload_swap_rejected():
    """Підміна payload (напр. role=admin) без секрета не пройде — підпис не збіжиться."""
    os.environ["JWT_SECRET"] = "test-secret-at-least-16-chars-long"
    t = auth.make_token(1, "user")
    h, _, s = t.split(".")
    forged_payload = auth._b64(b'{"sub":1,"role":"admin","iat":0,"exp":9999999999}')
    try:
        auth.verify_token(f"{h}.{forged_payload}.{s}")
        raise AssertionError("мала бути AuthError")
    except auth.AuthError:
        pass


def test_expired_rejected():
    os.environ["JWT_SECRET"] = "test-secret-at-least-16-chars-long"
    t = auth.make_token(1, "user", ttl_days=-1)  # уже протермінований
    try:
        auth.verify_token(t)
        raise AssertionError("мала бути AuthError")
    except auth.AuthError:
        pass


def test_different_secret_rejects():
    os.environ["JWT_SECRET"] = "secret-number-one-16plus-chars"
    t = auth.make_token(1, "user")
    os.environ["JWT_SECRET"] = "secret-number-two-16plus-chars"
    try:
        auth.verify_token(t)
        raise AssertionError("мала бути AuthError")
    except auth.AuthError:
        pass


def test_no_secret_refuses():
    os.environ.pop("JWT_SECRET", None)
    try:
        auth.make_token(1, "user")
        raise AssertionError("без JWT_SECRET токен видавати не можна")
    except auth.AuthError:
        pass


def test_bearer_claims_helper():
    os.environ["JWT_SECRET"] = "test-secret-at-least-16-chars-long"
    t = auth.make_token(7, "user")
    assert auth.bearer_claims(f"Bearer {t}")["sub"] == 7
    assert auth.bearer_claims(t) is None            # без «Bearer »
    assert auth.bearer_claims(None) is None
    assert auth.bearer_claims("Bearer garbage") is None


def _main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v) and getattr(v, "__module__", None) == __name__]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
