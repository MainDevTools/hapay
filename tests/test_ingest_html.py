"""Тести html-ingest — СЕРВЕР парсить переслане застосунком HTML (S11 етап 3).

Чисті (без БД): двофазний discover з хабу, валідація джерела/URL/схеми/розміру, план
збору. Персист-шлях (extract → БД → видно в /discounts) перевіряє живий test_api.

Головне: застосунок = «тупий фетчер». Він НЕ вирішує, що джерело валідне, і НЕ парсить —
сервер лишається авторитетом і над списком крамниць, і над екстракцією.

Запуск:  python tests/test_ingest_html.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import ingest as ing          # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")
HUB = "https://allo.ua/ua/events-and-discounts/"


def _read(name):
    with open(os.path.join(CAS, name), encoding="utf-8") as f:
        return f.read()


def _raises(fn, needle):
    try:
        fn()
    except ValueError as e:
        assert needle in str(e), f"очікував {needle!r} у {e!r}"
        return
    assert False, f"мало кинути ValueError із {needle!r}"


# ── план збору: сервер — авторитет над списком ────────────────────────────────────

def test_plan_lists_allo_hub():
    plan = ing.collect_plan()
    assert any(t["source"] == "Allo" and t["url"] == HUB and t["kind"] == "hub" for t in plan), plan


# ── фаза 1: хаб → сервер робить discover() ────────────────────────────────────────

def test_hub_html_returns_discovered_landings():
    r = ing.ingest_html(None, "Allo", HUB, _read("allo_hub.html"))
    assert r["kind"] == "hub" and r["accepted"] == 0, r
    assert len(r["discovered"]) == 9, r["discovered"]
    assert all(u.startswith("https://allo.ua/ua/events-and-discounts/") and u.endswith("-action/")
               for u in r["discovered"])


def test_discovered_landings_stay_on_store_domain():
    """Лендинги мусять лишатись на allo.ua — сервер не може збити застосунок на чужий хост."""
    r = ing.ingest_html(None, "Allo", HUB, _read("allo_hub.html"))
    assert all(u.startswith("https://allo.ua/") for u in r["discovered"]), r["discovered"]


# ── валідація: застосунок не може «вигадати» джерело чи підсунути чужий/битий вхід ─

def test_unknown_source_rejected():
    _raises(lambda: ing.ingest_html(None, "Хакер", HUB, "<html></html>"), "html-джерело")


def test_url_must_be_on_store_domain():
    _raises(lambda: ing.ingest_html(None, "Allo", "https://evil.example.com/x", "<html></html>"),
            "домені")


def test_url_must_be_https():
    _raises(lambda: ing.ingest_html(None, "Allo", "http://allo.ua/ua/events-and-discounts/",
                                    "<html></html>"), "https")


def test_empty_html_rejected():
    _raises(lambda: ing.ingest_html(None, "Allo", HUB, "   "), "порожн")


def test_oversized_html_rejected():
    big = "<html>" + "x" * (ing._MAX_HTML + 1)
    _raises(lambda: ing.ingest_html(None, "Allo", HUB, big), "завеликий")


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
