"""Тест ЗАПОБІЖНИКА (tests/dbguard.py) — того, що боронить прод від reset().

Це не формальність. 2026-07-17 руйнівний тест підхопив прод-`DATABASE_URL` із середовища
й дропнув живу історію цін (T13). Запобіжник — єдине, що тепер стоїть між
`python tests/test_api.py` і продом, тож він мусить перевірятись сам.

Запуск:  python tests/test_dbguard.py   (не потребує БД)
"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.dbguard import test_dsn, _TABLES, _target  # noqa: E402

PROD = "postgresql://user:s3cret@ep-still-cherry.eu-central-1.aws.neon.tech/neondb?sslmode=require"
PROD_ROTATED = "postgresql://user:NEW-pass@ep-still-cherry.eu-central-1.aws.neon.tech/neondb"
TEST = "postgresql://postgres:radar@localhost:5432/radar"


def _run(env: dict):
    """test_dsn із підміненим середовищем → ('ok', url) | ('exit', code). stdout глушимо."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        with redirect_stdout(io.StringIO()):
            return ("ok", test_dsn("проба"))
    except SystemExit as e:
        return ("exit", e.code)
    finally:
        os.environ.clear()
        os.environ.update(saved)


# ---- головна регресія: саме так ми знесли базу ----

def test_prod_url_alone_is_never_used():
    """DATABASE_URL сам по собі НЕ дає руйнівному тесту бази — тільки пропуск.
    Це точний сценарій T13: у середовищі був прод — тест його підхопив і дропнув."""
    assert _run({"DATABASE_URL": PROD}) == ("exit", 0)


def test_skip_without_test_url():
    assert _run({}) == ("exit", 0)


def test_test_url_is_used():
    assert _run({"TEST_DATABASE_URL": TEST}) == ("ok", TEST)


def test_both_set_but_different_is_ok():
    """Звична робоча ситуація: прод у .env, тестова база локально — працюємо."""
    assert _run({"TEST_DATABASE_URL": TEST, "DATABASE_URL": PROD}) == ("ok", TEST)


def test_same_target_refuses():
    assert _run({"TEST_DATABASE_URL": PROD, "DATABASE_URL": PROD}) == ("exit", 1)


def test_same_target_different_password_still_refuses():
    """Ротація пароля не робить базу іншою — порівнюємо host/db, не рядок цілком."""
    assert _run({"TEST_DATABASE_URL": PROD_ROTATED, "DATABASE_URL": PROD}) == ("exit", 1)


# ---- _target: порівнюємо ціль, не секрети ----

def test_target_has_host_and_db_but_no_password():
    t = _target(PROD)
    assert t == "ep-still-cherry.eu-central-1.aws.neon.tech/neondb", t
    assert "s3cret" not in t


def test_target_unparsed_is_conservative():
    """Нерозпізнані DSN вважаються однаковими → STOP. Краще відмовитись, ніж дропнути."""
    assert _target("що завгодно") == _target("зовсім інше") == "<unparsed>"


# ---- reset(): повнота переліку таблиць ----

def test_reset_covers_all_migrated_tables():
    """КОЖНА таблиця з міграцій мусить бути в _TABLES: DROP CASCADE по батьківській
    зносить лише FK, не залежну таблицю — пропущена переживає reset() без запису в
    schema_migration, і наступний migrate.apply падає на «already exists» (впіймано
    CI 2026-07-24: product_spec + чотири таблиці S9, приховані раннім збоєм CI)."""
    import re as _re
    mig_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "migrations")
    created: set[str] = set()
    for fname in os.listdir(mig_dir):
        if not fname.endswith(".sql"):
            continue
        with open(os.path.join(mig_dir, fname), encoding="utf-8") as f:
            sql = f.read()
        created |= {m.lower() for m in _re.findall(
            r"CREATE TABLE(?: IF NOT EXISTS)?\s+([a-zA-Z_]+)", sql, _re.I)}
    missing = created - set(_TABLES)
    assert not missing, f"таблиці з міграцій поза dbguard._TABLES: {sorted(missing)}"


def _main():
    # лише свої функції: імпортований test_dsn теж починається з «test_», але він не тест
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
