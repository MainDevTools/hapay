"""Тести ingest — токен-автентифікація + валідація елементів (чисті, без БД).

Головне: сервер НЕ вірить колектору на слово. Ці тести — доказ, що інʼєкцію
(чужий URL, абсурдна ціна, сміття) сервер відкидає ще до бази.

Запуск:  python tests/test_ingest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import ingest as ing          # noqa: E402


def _good(**over):
    base = {"external_ref": "/ua/products/x/foo.html",
            "url": "https://www.foxtrot.com.ua/ua/products/x/foo.html",
            "title": "Телевізор Samsung QE55", "price_now_kop": 4499900,
            "price_old_kop": 5299900, "in_stock": True,
            "image_url": "https://img.foxtrot.com.ua/a.webp"}
    base.update(over)
    return base


# ── токен-автентифікація ──────────────────────────────────────────────────────

def test_load_tokens_parses_pairs():
    os.environ["INGEST_TOKENS"] = "phone:abc123, friend:def456"
    t = ing.load_tokens()
    assert t == {"abc123": "phone", "def456": "friend"}


def test_unknown_token_rejected():
    os.environ["INGEST_TOKENS"] = "phone:secret-token"
    assert ing.collector_label("Bearer wrong") is None
    assert ing.collector_label(None) is None
    assert ing.collector_label("secret-token") is None       # без «Bearer »
    assert ing.collector_label("Bearer secret-token") == "phone"


def test_empty_tokens_env_denies_all():
    os.environ["INGEST_TOKENS"] = ""
    assert ing.collector_label("Bearer anything") is None


# ── валідація: інʼєкція має відсіятись ────────────────────────────────────────

def test_valid_item_passes():
    item, why = ing.validate_item("Foxtrot", _good())
    assert why is None and item is not None
    assert item.price_now_kop == 4499900 and item.price_old_kop == 5299900


def test_url_must_be_on_store_domain():
    """Ключовий захист: колектор не може вкинути чужий/фішинг-URL."""
    item, why = ing.validate_item("Foxtrot", _good(url="https://evil.example.com/x.html"))
    assert item is None and "домені" in why


def test_url_must_be_https():
    item, why = ing.validate_item("Foxtrot", _good(url="http://www.foxtrot.com.ua/x.html"))
    assert item is None and "https" in why


def test_absurd_price_rejected():
    assert ing.validate_item("Foxtrot", _good(price_now_kop=1))[0] is None          # < 1 грн
    assert ing.validate_item("Foxtrot", _good(price_now_kop=999_999_999))[0] is None  # > стелі
    assert ing.validate_item("Foxtrot", _good(price_now_kop="4499900"))[0] is None  # рядок
    assert ing.validate_item("Foxtrot", _good(price_now_kop=True))[0] is None       # bool не int-ціна


def test_old_not_above_now_becomes_none():
    item, why = ing.validate_item("Foxtrot", _good(price_old_kop=4000000))  # < now
    assert why is None and item.price_old_kop is None                        # не знижка


def test_empty_title_rejected():
    assert ing.validate_item("Foxtrot", _good(title="   "))[0] is None
    assert ing.validate_item("Foxtrot", _good(title=123))[0] is None


def test_bad_image_dropped_not_fatal():
    item, why = ing.validate_item("Foxtrot", _good(image_url="http://x/insecure.png"))
    assert why is None and item.image_url is None            # елемент лишається, фото нема


def test_subdomain_host_allowed():
    item, why = ing.validate_item("Rozetka", {
        "external_ref": "/p1", "url": "https://xl-catalog-api.rozetka.com.ua/p.html",
        "title": "x", "price_now_kop": 100000})
    assert why is None and item is not None                  # *.rozetka.com.ua — ok


def test_unknown_source_registry():
    assert "Foxtrot" in ing.INGEST_SOURCES and "Moyo" in ing.INGEST_SOURCES
    # валідація для невідомого джерела впаде на KeyError усередині — ловиться в ingest_batch
    try:
        ing.validate_item("НевідомаКрамниця", _good())
        raised = False
    except KeyError:
        raised = True
    assert raised


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
