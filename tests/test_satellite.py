"""Тест сателіт-передавача (collect_satellite) — на касетах, БЕЗ мережі й БД.

Доводить: сателіт бере satellite-джерела, будує коректний payload з екстрактора
і шле його `post`-функції (яку тут підміняємо, щоб не ходити в інтернет).

Запуск:  python tests/test_satellite.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collect import collect_satellite, SOURCES     # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _read(name):
    with open(os.path.join(CAS, name), encoding="utf-8") as f:
        return f.read()


def _fetch(url):
    if url.rstrip("/").endswith("events-and-discounts"):
        return _read("allo_hub.html")
    if "-action/" in url:
        return _read("allo_action.html")
    raise AssertionError(f"несподіваний URL: {url}")


def _run():
    captured = []

    def fake_post(ingest_url, token, payload):
        captured.append((ingest_url, token, payload))
        return {"source": payload["source"], "accepted": len(payload["items"]),
                "rejected": 0, "status": "ok"}

    results = collect_satellite(SOURCES, "https://hapay.today/api/ingest", "TESTTOKEN",
                                fetch=_fetch, delay=0, post=fake_post)
    return results, captured


# ── тести ─────────────────────────────────────────────────────────────────────

def test_only_satellite_sources():
    """Pethouse/PetChoice (satellite=False) НЕ чіпаємо; лише Allo (satellite=True)."""
    results, _ = _run()
    assert [r["source"] for r in results] == ["Allo"], results


def test_payload_shape_and_token():
    _, captured = _run()
    assert len(captured) == 1
    url, token, payload = captured[0]
    assert url == "https://hapay.today/api/ingest"
    assert token == "TESTTOKEN"
    assert payload["source"] == "Allo"
    assert len(payload["items"]) == 3                     # 3 unique з касети (дедуп)


def test_items_have_ingest_fields():
    _, captured = _run()
    item = captured[0][2]["items"][0]
    for k in ("external_ref", "url", "title", "price_now_kop", "price_old_kop", "in_stock"):
        assert k in item, k
    assert item["url"].startswith("https://allo.ua/")
    assert isinstance(item["price_now_kop"], int)


def test_reports_sent_and_server_response():
    results, _ = _run()
    r = results[0]
    assert r["sent"] == 3 and r["errors"] == []
    assert r["resp"]["accepted"] == 3


def test_post_failure_captured_not_raised():
    """Падіння POST не валить процес — фіксується в errors, sent усе одно відомий."""
    def boom(*a):
        raise RuntimeError("сервер недоступний")
    results = collect_satellite(SOURCES, "u", "t", fetch=_fetch, delay=0, post=boom)
    r = results[0]
    assert r["resp"] is None and any("POST" in e for e in r["errors"])


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
