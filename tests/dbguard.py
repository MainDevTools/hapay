"""Запобіжник для РУЙНІВНИХ тестів + спільний reset().

Чому окремий модуль: імпортується з чотирьох тестів, тому **не має побічних ефектів**
на імпорті (жодних sys.exit на рівні модуля).

── Навіщо це взагалі (T13, 2026-07-17) ───────────────────────────────────────────
Тести читали ту саму змінну, що й прод — `DATABASE_URL`. Достатньо було підставити
прод-рядок у середовище й запустити `python tests/test_api.py`, щоб `reset()` дропнув
живу базу. Так і сталось: історія цін (380 снапшотів) знищена.

Append-only тригер на `price_snapshot` тут НЕ рятує: він боронить від UPDATE/DELETE,
а `reset()` робить DROP TABLE. Єдиний надійний захист — щоб прод і тест **називались
по-різному**: руйнівні тести читають ЛИШЕ `TEST_DATABASE_URL` і ніколи `DATABASE_URL`.
"""
import os
import re
import sys

_TABLES = ("alert_log", "watchlist", "discount_event", "price_snapshot", "scan_run",
           "http_cache", "canary", "store_product", "source_category_map",
           "category", "source", "detection_config", "app_config", "schema_migration")


def _target(dsn: str) -> str:
    """host/db без секретів — щоб порівняти прод і тест, не друкуючи пароль.
    Нерозпізнане → '<unparsed>'; два нерозпізнані вважаються однаковими (безпечний бік:
    краще зайвий раз відмовитись, ніж дропнути прод)."""
    m = re.search(r"@([^/?@]+)/([^/?]+)", dsn or "")
    return f"{m.group(1)}/{m.group(2)}" if m else "<unparsed>"


def test_dsn(name: str) -> str:
    """DSN для тесту, який ДРОПАЄ ВСІ ТАБЛИЦІ. Дві незалежні перевірки:

    1. читаємо лише `TEST_DATABASE_URL` — прод-змінну свідомо не беремо;
    2. якщо він указує на ту саму базу, що `DATABASE_URL` — STOP, не дропаємо.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        print(f"SKIP {name}: TEST_DATABASE_URL не задано "
              f"(руйнівний тест; DATABASE_URL свідомо не читаємо — T13).")
        sys.exit(0)
    prod = os.environ.get("DATABASE_URL")
    if prod and _target(prod) == _target(url):
        print(f"STOP {name}: TEST_DATABASE_URL вказує на ту саму базу, що DATABASE_URL "
              f"({_target(url)}). Відмовляюсь дропати — підніми окрему тестову базу.")
        sys.exit(1)
    return url


def reset(conn):
    """ДРОПАЄ ВСІ ТАБЛИЦІ. Кликати лише з DSN, здобутим через test_dsn()."""
    stmts = ["DROP MATERIALIZED VIEW IF EXISTS price_daily CASCADE;"]
    stmts += [f"DROP TABLE IF EXISTS {t} CASCADE;" for t in _TABLES]
    stmts.append("DROP FUNCTION IF EXISTS trg_ps_append_only() CASCADE;")
    res = conn.pgconn.exec_("".join(stmts).encode())
    if res.error_message:
        pass  # IF EXISTS — безпечно
