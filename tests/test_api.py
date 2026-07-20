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
os.environ["JWT_SECRET"] = "test-jwt-secret-at-least-16-chars"  # для auth-ендпоінтів

import psycopg                                          # noqa: E402
from fastapi.testclient import TestClient               # noqa: E402
from db import migrate                                  # noqa: E402
from collect import collect, SOURCES                    # noqa: E402
from api.main import app                                # noqa: E402
from api import ingest as qingest                       # noqa: E402  (к-сть HTML_SOURCES)
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

    # ── акаунти (S11): реєстрація / логін / профіль / watchlist ───────────────────
    reg = client.post("/api/auth/register", json={"email": "Test@Hapay.today", "password": "supersecret"})
    checks.append(("register 200 + token", reg.status_code == 200 and "token" in reg.json(), reg.status_code))
    tok = reg.json().get("token", "")
    ahdr = {"Authorization": f"Bearer {tok}"}

    checks.append(("дубль email → 409",
                   client.post("/api/auth/register",
                               json={"email": "test@hapay.today", "password": "another1"}).status_code == 409, None))
    checks.append(("короткий пароль → 400",
                   client.post("/api/auth/register",
                               json={"email": "b@hapay.today", "password": "short"}).status_code == 400, None))

    lg = client.post("/api/auth/login", json={"email": "test@hapay.today", "password": "supersecret"})
    checks.append(("login (регістр email байдужий) → 200", lg.status_code == 200 and "token" in lg.json(), lg.status_code))
    checks.append(("login з невірним паролем → 401",
                   client.post("/api/auth/login",
                               json={"email": "test@hapay.today", "password": "WRONG"}).status_code == 401, None))

    checks.append(("/api/me без токена → 401", client.get("/api/me").status_code == 401, None))
    mer = client.get("/api/me", headers=ahdr).json()
    checks.append(("/api/me повертає email+role=user",
                   mer.get("email") == "test@hapay.today" and mer.get("role") == "user", mer))

    wa = client.post("/api/me/watchlist", json={"kind": "query", "query_text": "iphone"}, headers=ahdr)
    checks.append(("POST /api/me/watchlist → 200", wa.status_code == 200, wa.status_code))
    mwl = client.get("/api/me/watchlist", headers=ahdr).json()
    checks.append(("/api/me/watchlist повертає запис юзера",
                   len(mwl) == 1 and mwl[0]["query_text"] == "iphone", mwl))

    # ── html-ingest (S11 етап 3): гейт ролі collector + сервер парсить переслане HTML ──
    # ролі роздає власник напряму в БД (trusted-people) — робимо акаунт колектором
    client.post("/api/auth/register", json={"email": "collector@hapay.today", "password": "collectorpass"})
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("UPDATE app_user SET role='collector' WHERE lower(email)='collector@hapay.today'")
    clg = client.post("/api/auth/login",
                      json={"email": "collector@hapay.today", "password": "collectorpass"}).json()
    chdr = {"Authorization": f"Bearer {clg.get('token', '')}"}
    checks.append(("login колектора → role=collector", clg.get("role") == "collector", clg.get("role")))

    # план збору — гейт ролі: простому юзеру зась, колектору й статичному токену — так
    checks.append(("collect/plan простому юзеру → 401",
                   client.get("/api/collect/plan", headers=ahdr).status_code == 401, None))
    checks.append(("collect/plan статичним токеном колектора → 200 (сумісність S10)",
                   client.get("/api/collect/plan", headers=ing_tok).status_code == 200, None))
    plan = client.get("/api/collect/plan", headers=chdr).json()
    checks.append(("collect/plan колектору → Allo hub",
                   any(t["source"] == "Allo" and t["kind"] == "hub"
                       for t in plan.get("targets", [])), plan))

    def _cas(n):
        with open(os.path.join(os.path.dirname(__file__), "cassettes", n), encoding="utf-8") as f:
            return f.read()
    allo_hub, allo_action = _cas("allo_hub.html"), _cas("allo_action.html")
    HUB = "https://allo.ua/ua/events-and-discounts/"

    checks.append(("ingest/html без токена → 401",
                   client.post("/api/ingest/html",
                               json={"source": "Allo", "url": HUB, "html": allo_hub}).status_code == 401, None))
    checks.append(("ingest/html чужий хост у url → 400",
                   client.post("/api/ingest/html", headers=chdr,
                               json={"source": "Allo", "url": "https://evil.example.com/x",
                                     "html": allo_hub}).status_code == 400, None))

    # фаза 1: хаб → сервер робить discover() → 9 лендингів, нічого ще не персистить
    h1 = client.post("/api/ingest/html", json={"source": "Allo", "url": HUB, "html": allo_hub}, headers=chdr)
    hj = h1.json()
    checks.append(("ingest/html хаб → 9 лендингів, accepted=0",
                   h1.status_code == 200 and hj.get("kind") == "hub"
                   and len(hj.get("discovered", [])) == 9 and hj.get("accepted") == 0, hj))
    checks.append(("хаб кладе лендинги в чергу (enqueued=9, T16)",
                   hj.get("enqueued") == 9, hj.get("enqueued")))

    # фаза 2: один лендинг → СЕРВЕР extract → персист 3 товари
    landing = hj["discovered"][0]
    p1 = client.post("/api/ingest/html",
                     json={"source": "Allo", "url": landing, "html": allo_action}, headers=chdr)
    pj = p1.json()
    checks.append(("ingest/html лендинг → 3 прийнято (парсив сервер)",
                   p1.status_code == 200 and pj.get("kind") == "page" and pj.get("accepted") == 3, pj))
    checks.append(("ingest/html: колектор = acct:*",
                   str(pj.get("collector", "")).startswith("acct:"), pj.get("collector")))

    allo_seen = client.get("/api/discounts?q=REDMI").json()
    checks.append(("html-ingest товар видно в /discounts (store=Allo)",
                   len(allo_seen) >= 1 and allo_seen[0]["store"] == "Allo", allo_seen))

    # Foxtrot/Moyo (kind=page, без хаба): сервер парсить лістинг своїм адаптером
    fr = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Foxtrot", "url": "https://www.foxtrot.com.ua/uk/shop/mobilnye_telefony.html",
        "html": _cas("foxtrot_listing.html")})
    checks.append(("ingest/html Foxtrot-лістинг → 3 прийнято",
                   fr.status_code == 200 and fr.json().get("accepted") == 3, fr.json()))
    mr = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Moyo", "url": "https://www.moyo.ua/ua/telecommunication/smart/",
        "html": _cas("moyo_listing.html")})
    checks.append(("ingest/html Moyo-лістинг → 3 прийнято",
                   mr.status_code == 200 and mr.json().get("accepted") == 3, mr.json()))

    # Rozetka-лістинг: S26 SM-S942BZKGEUC збігається з Foxtrot (той самий MPN) →
    # ЖИВА крос-крамнична група «Де купити» з реальних адаптерів (не синтетика)
    rz = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Rozetka", "url": "https://rozetka.com.ua/ua/mobile-phones/c80003/",
        "html": _cas("rozetka_listing.html")})
    checks.append(("ingest/html Rozetka-лістинг → 3 прийнято",
                   rz.status_code == 200 and rz.json().get("accepted") == 3, rz.json()))
    s26 = client.get("/api/discounts?q=SM-S942BZKGEUC").json()
    # дедуп стрічки: S26 — ОДНА картка (не по одній на Rozetka й Foxtrot), offers_n=2
    checks.append(("S26 у стрічці ОДИН раз (дедуп групи), offers_n=2",
                   len(s26) == 1 and s26[0].get("offers_n") == 2, [(len(s26), s26[0].get("offers_n") if s26 else None)]))
    if s26:
        s26_off = client.get(f"/api/product/{s26[0]['store_product_id']}/offers").json()
        checks.append(("S26 група з РЕАЛЬНИХ адаптерів: {Rozetka, Foxtrot}",
                       {o["store"] for o in s26_off} == {"Rozetka", "Foxtrot"},
                       [o["store"] for o in s26_off]))

    # ── агрегатна картка за MPN (T15/§17.5): той самий товар у 2 крамницях ────────
    # Allo (html-ingest вище) має Samsung A37 SM-A376BDGGEUC. Запит ПОВНИМ MPN:
    # у Moyo-касеті інший варіант A37 (…BZABEUC) — він НЕ мусить потрапити ні сюди,
    # ні в групу (різні артикули = різні товари).
    a37 = client.get("/api/discounts?q=SM-A376BDGGEUC").json()
    checks.append(("Allo A37 (повний MPN) у вітрині — рівно 1", len(a37) == 1, len(a37)))
    a37_id = a37[0]["store_product_id"]

    # до другої крамниці: offers повертає лише сам товар (група з 1)
    solo = client.get(f"/api/product/{a37_id}/offers").json()
    checks.append(("offers до 2-ї крамниці: група з 1 (сам товар)",
                   len(solo) == 1 and solo[0]["store"] == "Allo", solo))

    # Foxtrot продає ТОЙ САМИЙ товар (той самий MPN у назві) дешевше
    client.post("/api/ingest", headers=ing_tok, json={"source": "Foxtrot", "items": [
        {"external_ref": "/ua/shop/samsung-a37-256.html",
         "url": "https://www.foxtrot.com.ua/ua/shop/samsung-a37-256.html",
         "title": "Samsung Galaxy A37 5G 8/256GB Awesome Graphite (SM-A376BDGGEUC)",
         "price_now_kop": 1999900}]})
    duo = client.get(f"/api/product/{a37_id}/offers").json()
    checks.append(("offers після 2-ї крамниці: 2 офери",
                   len(duo) == 2 and {o["store"] for o in duo} == {"Allo", "Foxtrot"}, duo))
    checks.append(("offers сортовано від найдешевшої (Foxtrot перший)",
                   len(duo) == 2 and duo[0]["store"] == "Foxtrot"
                   and duo[0]["current_kop"] == 1999900
                   and duo[0]["current_kop"] <= duo[1]["current_kop"], duo))

    # стрічка знає розмір групи: offers_n=2 у картці A37 (для «Наявно в 2 крамницях»)
    a37_after = client.get("/api/discounts?q=SM-A376BDGGEUC").json()
    checks.append(("discounts.offers_n = 2 після 2-ї крамниці",
                   len(a37_after) == 1 and a37_after[0].get("offers_n") == 2,
                   [d.get("offers_n") for d in a37_after]))
    pet_n = client.get("/api/discounts?q=Royal").json()
    checks.append(("товар без MPN → offers_n = 1",
                   all(d.get("offers_n") == 1 for d in pet_n), [d.get("offers_n") for d in pet_n]))

    # регіональний суфікс НЕ зливається (пастка AUXUA): третя позиція з іншим суфіксом
    client.post("/api/ingest", headers=ing_tok, json={"source": "Moyo", "items": [
        {"external_ref": "/ua/samsung-a37-ua.html",
         "url": "https://www.moyo.ua/ua/samsung-a37-ua.html",
         "title": "Samsung Galaxy A37 5G 8/256GB (SM-A376BDGGAUXUA)",
         "price_now_kop": 1899900}]})
    still = client.get(f"/api/product/{a37_id}/offers").json()
    checks.append(("AUXUA-суфікс НЕ злився у групу (лишилось 2)", len(still) == 2, len(still)))

    # товар без MPN (зоо) → offers порожній, блок не показується
    pet = client.get("/api/discounts?q=Royal").json()
    if pet:
        po = client.get(f"/api/product/{pet[0]['store_product_id']}/offers").json()
        checks.append(("товар без MPN → offers = []", po == [], po))

    # та сама крамниця, 2 кольори з РОДОВИМ артикулом (OPPO CPH2801) → НЕ група:
    # offers = 1 крамниця (дедуп), offers_n = 1 (рахуємо крамниці, не товари)
    # знижкові (old>now), щоб потрапили у /discounts і перевірки нижче реально відпрацювали
    client.post("/api/ingest", headers=ing_tok, json={"source": "Foxtrot", "items": [
        {"external_ref": "/ua/shop/oppo-reno15f-black.html",
         "url": "https://www.foxtrot.com.ua/ua/shop/oppo-reno15f-black.html",
         "title": "Смартфон OPPO Reno 15 F 8/256GB Black (CPH2801)",
         "price_now_kop": 1749900, "price_old_kop": 1899900},
        {"external_ref": "/ua/shop/oppo-reno15f-blue.html",
         "url": "https://www.foxtrot.com.ua/ua/shop/oppo-reno15f-blue.html",
         "title": "Смартфон OPPO Reno 15 F 8/256GB Blue (CPH2801)",
         "price_now_kop": 1749900, "price_old_kop": 1899900}]})
    oppo = client.get("/api/discounts?q=CPH2801").json()
    # дедуп: 2 кольори 1 крамниці → ОДНА картка (не дві), offers_n=1 (крамниця одна)
    checks.append(("OPPO у стрічці ОДИН раз (дедуп кольорів)", len(oppo) == 1, len(oppo)))
    checks.append(("2 кольори 1 крамниці → offers_n=1 (не бреше про 2 крамниці)",
                   bool(oppo) and all(d.get("offers_n") == 1 for d in oppo),
                   [d.get("offers_n") for d in oppo]))
    if oppo:
        oo = client.get(f"/api/product/{oppo[0]['store_product_id']}/offers").json()
        checks.append(("«Де купити»: одна пропозиція на крамницю (дедуп Foxtrot)",
                       len(oo) == 1 and oo[0]["store"] == "Foxtrot", [o["store"] for o in oo]))

    # ── черга-оренда (T16 крок 1): lease → ingest(task_id) → закриття ─────────────
    checks.append(("lease простому юзеру → 401",
                   client.post("/api/collect/lease", headers=ahdr, json={}).status_code == 401, None))
    lr = client.post("/api/collect/lease", json={"limit": 20}, headers=chdr).json()
    ltasks = lr.get("tasks", [])
    lsrc = [t["source"] for t in ltasks]
    checks.append(("lease колектору → по 1 задачі на крамницю (усі джерела HTML_SOURCES)",
                   len(ltasks) == len(qingest.HTML_SOURCES) and len(lsrc) == len(set(lsrc)), lsrc))
    checks.append(("lease віддає mode: Brain=render, Foxtrot=fetch (WebView-режим)",
                   next((t["mode"] for t in ltasks if t["source"] == "Brain"), None) == "render"
                   and next((t["mode"] for t in ltasks if t["source"] == "Foxtrot"), None) == "fetch",
                   [(t["source"], t.get("mode")) for t in ltasks]))
    checks.append(("повторний lease одразу → порожньо (розліт 15 хв)",
                   client.post("/api/collect/lease", json={"limit": 20},
                               headers=chdr).json().get("tasks") == [], None))

    fox_task = next((t for t in ltasks if t["source"] == "Foxtrot"), None)
    checks.append(("у lease є задача Foxtrot", fox_task is not None, ltasks))
    if fox_task:
        tr = client.post("/api/ingest/html", headers=chdr, json={
            "source": "Foxtrot", "url": fox_task["url"],
            "html": _cas("foxtrot_listing.html"), "task_id": fox_task["task_id"]})
        checks.append(("ingest/html із task_id → задача закрита",
                       tr.status_code == 200 and tr.json().get("task_closed") is True, tr.json()))

    allo_task = next((t for t in ltasks if t["source"] == "Allo"), None)
    if allo_task and allo_task["kind"] == "hub":
        hr = client.post("/api/ingest/html", headers=chdr, json={
            "source": "Allo", "url": allo_task["url"], "html": allo_hub,
            "task_id": allo_task["task_id"]}).json()
        # лендинги ВЖЕ в черзі з першого хаб-виклику → повтор ідемпотентний (0 нових)
        checks.append(("хаб через чергу: задача закрита, enqueue ідемпотентний",
                       hr.get("task_closed") is True and hr.get("enqueued") == 0, hr))

    moyo_task = next((t for t in ltasks if t["source"] == "Moyo"), None)
    if moyo_task:
        fl = client.post("/api/collect/fail", headers=chdr,
                         json={"task_id": moyo_task["task_id"], "note": "HTTP 403"})
        checks.append(("collect/fail → ok (бекоф)", fl.status_code == 200, fl.status_code))

    qs = client.get("/api/collect/queue", headers=chdr).json()
    checks.append(("collect/queue: зріз по крамницях",
                   {s["source"] for s in qs.get("sources", [])} >= {"Allo", "Foxtrot", "Moyo"},
                   qs))

    # ── усі товари, не лише знижки (/api/products) ────────────────────────────────
    prods = client.get("/api/products?sort=new").json()
    disc = client.get("/api/discounts?sort=new").json()
    checks.append(("/products ⊇ /discounts (усі товари ≥ знижки)",
                   len(prods) >= len(disc) and len(prods) >= 1, (len(prods), len(disc))))
    # Foxtrot-лістинг мав Xiaomi Redmi 15C БЕЗ знижки → у /products є, у /discounts нема
    nd = client.get("/api/products?q=Redmi 15C").json()
    checks.append(("не-знижковий товар у /products (has_discount=false)",
                   len(nd) >= 1 and nd[0].get("has_discount") is False, nd))
    checks.append(("той самий БЕЗ знижки — НЕ в /discounts",
                   client.get("/api/discounts?q=Redmi 15C").json() == [], None))
    od = client.get("/api/products?only_discounts=1").json()
    checks.append(("only_discounts=1 звужує вибірку", len(od) < len(prods) and len(od) >= 1,
                   (len(od), len(prods))))
    checks.append(("/products має offers_n і badge", all("offers_n" in x and "badge_state" in x
                   for x in prods[:3]), list(prods[0]) if prods else None))
    # сорт «дешевші» — неспадна ціна
    cheap = client.get("/api/products?sort=cheap").json()
    checks.append(("sort=cheap: ціни неспадні",
                   all(cheap[i]["current_kop"] <= cheap[i+1]["current_kop"] for i in range(len(cheap)-1)),
                   [c["current_kop"] for c in cheap[:4]]))

    # ── дата акції (promo_until) — показуємо лише реальну (майбутню, ≤90 днів) ─────
    from datetime import date, timedelta
    near = (date.today() + timedelta(days=5)).isoformat()
    far = (date.today() + timedelta(days=200)).isoformat()
    client.post("/api/ingest", headers=ing_tok, json={"source": "Rozetka", "items": [
        {"external_ref": "/ua/promo-near/p1", "url": "https://rozetka.com.ua/ua/promo-near/p1/",
         "title": "Тест акція near (SM-TESTNEAR)", "price_now_kop": 1000000,
         "price_old_kop": 1200000, "promo_until": near},
        {"external_ref": "/ua/promo-far/p2", "url": "https://rozetka.com.ua/ua/promo-far/p2/",
         "title": "Тест акція far (SM-TESTFAR)", "price_now_kop": 1000000,
         "price_old_kop": 1200000, "promo_until": far}]})
    pn = client.get("/api/products?q=TESTNEAR").json()
    pf = client.get("/api/products?q=TESTFAR").json()
    checks.append(("promo_until: близька дата акції показується",
                   len(pn) == 1 and pn[0].get("promo_until") == near, pn))
    checks.append(("promo_until: далека (генерична) дата відсіяна",
                   len(pf) == 1 and pf[0].get("promo_until") is None, pf))

    # ── фільтр ціни (копійки) ─────────────────────────────────────────────────────
    all_now = client.get("/api/discounts?sort=new").json()
    expensive = client.get("/api/discounts?sort=new&price_min=4000000").json()   # ≥ 40 000 ₴
    cheap = client.get("/api/discounts?sort=new&price_max=100000").json()        # ≤ 1 000 ₴
    checks.append(("price_min: усі ≥ поріг", all(d["current_kop"] >= 4000000 for d in expensive), len(expensive)))
    checks.append(("price_max: усі ≤ поріг", all(d["current_kop"] <= 100000 for d in cheap), len(cheap)))
    checks.append(("price_min звужує вибірку", len(expensive) < len(all_now) and len(expensive) >= 1,
                   (len(expensive), len(all_now))))
    band = client.get("/api/discounts?sort=new&price_min=1000000&price_max=2000000").json()  # 10k–20k ₴
    checks.append(("price діапазон: усі в межах",
                   all(1000000 <= d["current_kop"] <= 2000000 for d in band), len(band)))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
