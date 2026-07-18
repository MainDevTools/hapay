"""Інтеграційний тест read-API проти живого Timescale (§8.10.1). Skip-aware (CI).

Дані сіє collect на касеті; API через FastAPI TestClient. Перевіряє перелік знижок,
історію, гейт initData на watchlist.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.dbguard import reset, test_dsn               # noqa: E402
URL = test_dsn("test_api")                              # РУЙНІВНИЙ: нижче reset() дропає все

os.environ["BOT_TOKEN"] = "123456:TEST-token"           # до імпорту app (читається на імпорті)
os.environ["DATABASE_URL"] = URL                        # api/db.py ходить у ТЕСТОВУ базу, не в прод
os.environ["INGEST_TOKENS"] = "tester:secret-ingest-token"   # довірений колектор для тесту

import psycopg                                          # noqa: E402
from fastapi.testclient import TestClient               # noqa: E402
from db import migrate                                  # noqa: E402
from collect import collect, SOURCES                    # noqa: E402
from api.main import app                                # noqa: E402
from api.initdata import build_init_data                # noqa: E402


def main():
    # сід даних (8 declared-подій)
    with psycopg.connect(URL, autocommit=True) as conn:
        reset(conn)
    migrate.apply(URL)
    with open(os.path.join(os.path.dirname(__file__), "cassettes", "pethouse_akcii.html"),
              encoding="utf-8") as f:
        cassette = f.read()
    with psycopg.connect(URL, autocommit=True) as conn:
        collect(conn, SOURCES, fetch=lambda u: cassette, delay=0)
        cat = conn.execute("SELECT category_id FROM category WHERE slug='uncategorized'").fetchone()[0]

    client = TestClient(app)
    checks, failed = [], 0

    checks.append(("health", client.get("/api/health").json() == {"ok": True}, None))

    disc = client.get("/api/discounts").json()
    checks.append(("перелік = 8 declared", len(disc) == 8 and all(d["badge_state"] == "declared" for d in disc), len(disc)))
    checks.append(("картка має поля §9.1", all(k in disc[0] for k in
                  ("title", "current_kop", "old_declared_kop", "badge_state", "image_url", "store")), list(disc[0])))

    filtered = client.get("/api/discounts?badge=declared").json()
    checks.append(("фільтр badge=declared", len(filtered) == 8, len(filtered)))

    spid = disc[0]["store_product_id"]
    hist = client.get(f"/api/product/{spid}/history").json()
    checks.append(("історія товару ≥1 доба", len(hist) >= 1 and "min_kop" in hist[0], hist))

    cats = client.get("/api/categories").json()
    checks.append(("категорії з активними знижками (koty-suhyi-korm)",
                   any(c["slug"] == "koty-suhyi-korm" and c["n"] > 0 for c in cats), cats))

    # фільтр за категорією
    only = client.get("/api/discounts?category=koty-suhyi-korm").json()
    checks.append(("фільтр за категорією повертає товари", len(only) >= 1, len(only)))

    # пошук за назвою
    srch = client.get("/api/discounts?q=Royal").json()
    checks.append(("пошук q=Royal", len(srch) >= 1 and all("Royal" in d["title"] for d in srch), len(srch)))
    checks.append(("пошук неіснуючого → порожньо", client.get("/api/discounts?q=zzz-нема").json() == [], None))

    # пагінація: 8 подій < 50 → page=1 порожня
    checks.append(("пагінація page=1 порожня", client.get("/api/discounts?page=1").json() == [], None))

    # watchlist без initData → 401
    checks.append(("watchlist без initData → 401", client.get("/api/watchlist").status_code == 401, None))

    # watchlist з валідною initData → 200 + запис
    init = build_init_data("123456:TEST-token", {"auth_date": int(time.time()), "user": {"id": 7, "first_name": "T"}})
    hdr = {"X-Init-Data": init}
    r = client.post("/api/watchlist", json={"kind": "category", "ref_id": cat}, headers=hdr)
    checks.append(("POST watchlist з initData → 200", r.status_code == 200, r.status_code))
    wl = client.get("/api/watchlist", headers=hdr).json()
    checks.append(("watchlist повертає 1 запис", len(wl) == 1 and wl[0]["kind"] == "category", wl))

    # ── ingest (S10): токен-гейт + валідація + персист ────────────────────────────
    ibody = {"source": "Foxtrot", "items": [
        {"external_ref": "/ua/shop/tv-samsung-qe55.html",
         "url": "https://www.foxtrot.com.ua/ua/shop/tv-samsung-qe55.html",
         "title": "Телевізор Samsung QE55QN80F", "price_now_kop": 4499900,
         "price_old_kop": 5299900, "image_url": "https://img.foxtrot.com.ua/a.webp"},
        {"external_ref": "/evil", "url": "https://evil.example.com/x.html",   # інʼєкція
         "title": "Фейк", "price_now_kop": 100},
    ]}
    ing_tok = {"Authorization": "Bearer secret-ingest-token"}

    checks.append(("ingest без токена → 401",
                   client.post("/api/ingest", json=ibody).status_code == 401, None))
    checks.append(("ingest із чужим токеном → 401",
                   client.post("/api/ingest", json=ibody,
                               headers={"Authorization": "Bearer nope"}).status_code == 401, None))

    ir = client.post("/api/ingest", json=ibody, headers=ing_tok)
    ij = ir.json()
    checks.append(("ingest 200: 1 прийнято, 1 відкинуто (чужий домен)",
                   ir.status_code == 200 and ij["accepted"] == 1 and ij["rejected"] == 1, ij))
    checks.append(("ingest: колектор = tester", ij.get("collector") == "tester", ij.get("collector")))

    fox = client.get("/api/discounts?q=QE55QN80F").json()
    checks.append(("ingest-товар видно в /discounts",
                   len(fox) == 1 and fox[0]["store"] == "Foxtrot"
                   and fox[0]["current_kop"] == 4499900, fox))

    checks.append(("ingest невідомого джерела → 400",
                   client.post("/api/ingest", json={"source": "Хакер", "items": []},
                               headers=ing_tok).status_code == 400, None))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
