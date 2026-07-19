"""Автентифікація (S11): хеш паролів + JWT (HS256). Без зовнішніх пакетів — stdlib.

Принципи:
- Пароль НІКОЛИ не в plaintext: pbkdf2_sha256, 600k ітерацій (OWASP-рівень), унікальна сіль.
- JWT — стандартний HS256 (той самий hmac-sha256, що в initdata.py), сумісний із будь-якою
  JWT-бібліотекою на боці застосунку. Секрет — `JWT_SECRET` з env; без нього токени НЕ видаємо.
- Порівняння — constant-time (hmac.compare_digest) проти timing-атак.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

_ALG = "pbkdf2_sha256"
_ITER = 600_000                       # OWASP-рекомендація для PBKDF2-HMAC-SHA256 (2023+)
MIN_PASSWORD = 8


# ── base64url без padding (як у JWT) ─────────────────────────────────────────────
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── паролі ───────────────────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, _ITER)
    return f"{_ALG}${_ITER}${_b64(salt)}${_b64(dk)}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        alg, iters, salt_b64, hash_b64 = stored.split("$")
        if alg != _ALG:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), _unb64(salt_b64), int(iters))
        return hmac.compare_digest(dk, _unb64(hash_b64))
    except Exception:
        return False


# ── JWT (HS256) ───────────────────────────────────────────────────────────────────
class AuthError(Exception):
    pass


def _secret() -> bytes:
    s = os.environ.get("JWT_SECRET", "")
    if len(s) < 16:
        raise AuthError("JWT_SECRET не заданий або закороткий (≥16 симв.) — токени не видаємо")
    return s.encode("utf-8")


def make_token(user_id: int, role: str, ttl_days: int = 30) -> str:
    now = int(time.time())
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps(
        {"sub": user_id, "role": role, "iat": now, "exp": now + ttl_days * 86400},
        separators=(",", ":")).encode("utf-8"))
    seg = f"{header}.{payload}"
    sig = _b64(hmac.new(_secret(), seg.encode("utf-8"), hashlib.sha256).digest())
    return f"{seg}.{sig}"


def verify_token(token: str) -> dict:
    """Повертає claims або кидає AuthError. Перевіряє підпис І термін дії."""
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise AuthError("невірний формат токена")
    seg = f"{parts[0]}.{parts[1]}"
    expected = _b64(hmac.new(_secret(), seg.encode("utf-8"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        raise AuthError("невірний підпис")
    try:
        claims = json.loads(_unb64(parts[1]))
    except Exception:
        raise AuthError("невірний payload")
    if int(claims.get("exp", 0)) < int(time.time()):
        raise AuthError("токен протермінований")
    return claims


def bearer_claims(authorization: str | None) -> dict | None:
    """`Authorization: Bearer <jwt>` → claims або None (невалідний/відсутній)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return verify_token(authorization[7:].strip())
    except AuthError:
        return None
