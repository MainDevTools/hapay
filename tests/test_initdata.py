"""Юніт-тести верифікації Telegram initData (§8.10.1). Чистий stdlib, без БД/FastAPI.

Запуск:  python tests/test_initdata.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.initdata import (verify_init_data, check_auth_age, build_init_data,  # noqa: E402
                          InitDataError)

TOKEN = "123456:TEST-bot-token-abcDEF"


def test_valid_signature_and_user_parsed():
    init = build_init_data(TOKEN, {"auth_date": 1000, "user": {"id": 42, "first_name": "Оля"}})
    p = verify_init_data(init, TOKEN)
    assert p["user"]["id"] == 42 and p["user"]["first_name"] == "Оля"


def test_tampered_data_rejected():
    init = build_init_data(TOKEN, {"auth_date": 1000, "user": {"id": 42}})
    tampered = init.replace("id%22%3A42", "id%22%3A99")  # підмінили user id → підпис не збіжиться
    try:
        verify_init_data(tampered, TOKEN)
        assert False, "мала впасти"
    except InitDataError:
        pass


def test_wrong_token_rejected():
    init = build_init_data(TOKEN, {"auth_date": 1000, "user": {"id": 1}})
    try:
        verify_init_data(init, "999:other-token")
        assert False, "мала впасти"
    except InitDataError:
        pass


def test_missing_hash_rejected():
    try:
        verify_init_data("auth_date=1000&user=%7B%7D", TOKEN)
        assert False
    except InitDataError:
        pass


def test_auth_age_fresh_vs_stale():
    p = {"auth_date": "1000"}
    check_auth_age(p, now_ts=1000 + 100, max_age_s=86400)          # свіже — ок
    try:
        check_auth_age(p, now_ts=1000 + 200000, max_age_s=86400)   # протухле
        assert False
    except InitDataError:
        pass


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
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
