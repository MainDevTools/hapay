"""Верифікація Telegram Mini App `initData` (§8.10.1) — чистий stdlib, без FastAPI.

Алгоритм (docs.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):
  secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)
де data_check_string — усі пари key=value (крім hash), відсортовані, з'єднані '\n'.
Клієнт НЕ має токена БД — особу дає лише підписана Telegram initData.
"""
from __future__ import annotations
import hashlib
import hmac
import json
from urllib.parse import parse_qsl


class InitDataError(Exception):
    pass


def verify_init_data(init_data: str, bot_token: str, max_age_s: int = 86400) -> dict:
    """Повертає розпарсений payload (з полем `user` як dict) якщо підпис валідний і свіжий.
    Кидає InitDataError інакше. `now_ts` — інжектований час для тестів."""
    if not bot_token:
        raise InitDataError("bot_token порожній")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("немає hash")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise InitDataError("невалідний підпис")

    payload = dict(pairs)
    if "user" in payload:
        try:
            payload["user"] = json.loads(payload["user"])
        except json.JSONDecodeError:
            raise InitDataError("зіпсований user")
    return payload


def check_auth_age(payload: dict, now_ts: int, max_age_s: int = 86400) -> None:
    """Свіжість auth_date (проти реплею старої initData). now_ts інжектується (тест)."""
    try:
        auth_date = int(payload.get("auth_date", 0))
    except (TypeError, ValueError):
        raise InitDataError("немає/битий auth_date")
    if now_ts - auth_date > max_age_s:
        raise InitDataError("initData протухла")


def build_init_data(bot_token: str, params: dict) -> str:
    """Підписати initData тим самим алгоритмом — ЛИШЕ для тестів (імітує клієнта Telegram)."""
    items = {k: (json.dumps(v, separators=(",", ":"), ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))
             for k, v in params.items()}
    dcs = "\n".join(f"{k}={items[k]}" for k in sorted(items))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret_key, dcs.encode(), hashlib.sha256).hexdigest()
    items["hash"] = h
    from urllib.parse import urlencode
    return urlencode(items)
