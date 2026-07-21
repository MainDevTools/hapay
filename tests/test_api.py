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
    # сітка-каталог (§17): кожна категорія несе розділ + іконку + поле фото-представника
    checks.append(("категорії несуть section+icon",
                   all(c.get("section") and c.get("icon") for c in cats), cats))
    checks.append(("категорії несуть image_url (фото плитки; може бути null)",
                   all("image_url" in c for c in cats), [list(c) for c in cats[:2]]))
    koty = next((c for c in cats if c["slug"] == "koty-suhyi-korm"), None)
    checks.append(("koty-suhyi-korm → розділ «Зоотовари»",
                   koty is not None and koty["section"] == "Зоотовари", koty))

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

    # ── «Стежити за ціною»: ціну фіксує СЕРВЕР, не клієнт ─────────────────────────
    prod = client.get("/api/discounts?q=QE55QN80F").json()[0]
    spid = prod["store_product_id"]
    w1 = client.post("/api/me/watchlist",
                     json={"kind": "store_product", "ref_id": spid}, headers=ahdr)
    checks.append(("watch товару → ціну зафіксовано сервером",
                   w1.status_code == 200
                   and w1.json().get("price_at_add_kop") == prod["current_kop"], w1.json()))
    # клієнт НЕ може продиктувати «стару» ціну (інакше намалював би фейкову економію)
    w_fake = client.post("/api/me/watchlist", headers=ahdr,
                         json={"kind": "store_product", "ref_id": spid,
                               "price_at_add_kop": 99999999})
    checks.append(("ціну з тіла запиту ігноруємо",
                   w_fake.json().get("price_at_add_kop") == prod["current_kop"], w_fake.json()))
    checks.append(("повторний watch не дублює запис",
                   w_fake.json().get("watchlist_id") == w1.json().get("watchlist_id"),
                   (w1.json().get("watchlist_id"), w_fake.json().get("watchlist_id"))))
    checks.append(("store_product без ref_id → 400",
                   client.post("/api/me/watchlist", json={"kind": "store_product"},
                               headers=ahdr).status_code == 400, None))

    wl = client.get("/api/me/watchlist", headers=ahdr).json()
    wit = next((x for x in wl if x["kind"] == "store_product"), None)
    checks.append(("список стеження збагачено (назва/ціна/delta)",
                   wit is not None and wit["title"] and wit["current_kop"] == prod["current_kop"]
                   and wit["delta_kop"] == 0, wit))

    # ── сповіщення про зниження ціни ─────────────────────────────────────────────
    def _drop_price(to_kop):
        """Ціна впала. price_snapshot append-only → пишемо НОВИЙ рядок, старі не чіпаємо."""
        with psycopg.connect(URL, autocommit=True) as c:
            c.execute("INSERT INTO price_snapshot (store_product_id, price_now_kop, in_stock, "
                      "source_method, seen_at, is_backfill) "
                      "VALUES (%s,%s,TRUE,'satellite',now(),FALSE)", (spid, to_kop))

    checks.append(("без руху ціни сповіщати нема про що",
                   client.get("/api/me/watchlist/drops", headers=ahdr).json() == [], None))

    _drop_price(prod["current_kop"] - 100000)          # −1000 грн
    d1 = client.get("/api/me/watchlist/drops", headers=ahdr).json()
    checks.append(("зниження помічено, різниця порахована",
                   len(d1) == 1 and d1[0]["drop_kop"] == 100000, d1))

    ack = client.post("/api/me/watchlist/drops/ack", headers=ahdr,
                      json={"watchlist_ids": [d1[0]["watchlist_id"]]})
    checks.append(("ack → 1", ack.json().get("acked") == 1, ack.json()))
    # головне: про ТЕ САМЕ зниження не турбуємо вдруге (інакше дзвонило б щогодини)
    checks.append(("те саме зниження вдруге НЕ турбує",
                   client.get("/api/me/watchlist/drops", headers=ahdr).json() == [], None))

    _drop_price(prod["current_kop"] - 150000)          # впало ще на 500 грн
    d2 = client.get("/api/me/watchlist/drops", headers=ahdr).json()
    checks.append(("подальше зниження — нове сповіщення (від попереднього рівня)",
                   len(d2) == 1 and d2[0]["drop_kop"] == 50000, d2))

    _drop_price(prod["current_kop"])                    # ціна повернулась — не сповіщаємо
    checks.append(("подорожчання назад не сповіщає",
                   client.get("/api/me/watchlist/drops", headers=ahdr).json() == [], None))

    checks.append(("ack чужого запису нічого не змінює",
                   client.post("/api/me/watchlist/drops/ack", headers=ahdr,
                               json={"watchlist_ids": [999999]}).json().get("acked") == 0, None))
    checks.append(("ack з не-списком → 400",
                   client.post("/api/me/watchlist/drops/ack", headers=ahdr,
                               json={"watchlist_ids": "abc"}).status_code == 400, None))

    # чуже стеження не видаляється — інакше будь-хто чистив би чужі списки
    other = client.post("/api/auth/register",
                        json={"email": "watcher2@hapay.today", "password": "watchpass"}).json()
    ohdr = {"Authorization": f"Bearer {other.get('token', '')}"}
    checks.append(("чужий запис стеження не видаляється → 404",
                   client.delete(f"/api/me/watchlist/{wit['watchlist_id']}",
                                 headers=ohdr).status_code == 404, None))
    checks.append(("свій запис видаляється → 200",
                   client.delete(f"/api/me/watchlist/{wit['watchlist_id']}",
                                 headers=ahdr).status_code == 200, None))

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
    # категорія-з-лістинга: смартфон-URL Foxtrot тегнутий «smartfony» → 3 товари лягли туди
    # (а не в «Інше», як було, коли таксономія була зоо-only). TV вище зайшов JSON-ingest
    # без тегу → categorize()→inshe, тож рахуємо саме smartfony-товари цього джерела.
    with psycopg.connect(URL, autocommit=True) as conn:
        fox_smart = conn.execute(
            "SELECT count(*) FROM store_product sp "
            "JOIN category c USING (category_id) JOIN source s USING (source_id) "
            "WHERE s.name='Foxtrot' AND c.slug='smartfony'").fetchone()[0]
    checks.append(("Foxtrot html-лістинг → 3 товари в smartfony (не Інше)",
                   fox_smart == 3, fox_smart))
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
    # офери несуть стару ціну по крамниці (для «ціна зі знижкою + перекреслена стара» в «Де купити»)
    fox_off = next((o for o in duo if o["store"] == "Foxtrot"), None)
    checks.append(("Foxtrot-оффер (без старої ціни) → old_declared_kop = None",
                   fox_off is not None and "old_declared_kop" in fox_off
                   and fox_off["old_declared_kop"] is None, fox_off))
    allo_off = next((o for o in duo if o["store"] == "Allo"), None)
    checks.append(("Allo-оффер несе ту саму стару ціну, що й картка A37",
                   allo_off is not None
                   and allo_off["old_declared_kop"] == a37[0].get("old_declared_kop"),
                   (allo_off.get("old_declared_kop") if allo_off else None, a37[0].get("old_declared_kop"))))

    # стрічка знає розмір групи: offers_n=2 у картці A37 (для «Наявно в 2 крамницях»)
    a37_after = client.get("/api/discounts?q=SM-A376BDGGEUC").json()
    checks.append(("discounts.offers_n = 2 після 2-ї крамниці",
                   len(a37_after) == 1 and a37_after[0].get("offers_n") == 2,
                   [d.get("offers_n") for d in a37_after]))
    pet_n = client.get("/api/discounts?q=Royal").json()
    checks.append(("товар без MPN → offers_n = 1",
                   all(d.get("offers_n") == 1 for d in pet_n), [d.get("offers_n") for d in pet_n]))

    # «Популярні моделі» (§17): сорт за розміром групи — найбільша к-сть крамниць першою
    pop = client.get("/api/products?sort=popular").json()
    checks.append(("sort=popular: найбільша група першою",
                   len(pop) >= 1
                   and pop[0].get("offers_n", 0) == max(d.get("offers_n", 0) for d in pop),
                   [d.get("offers_n") for d in pop[:5]]))

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

    # Ручний прохід «зібрати все» ходить за ПЛАНОМ і task_id не має. Сторінку він таки
    # збирає, тож задача мусить закритись за (source, url) — інакше черга перезбирала б
    # її вдруге, а last_done_at показував би «ще не брали». Так і було на проді
    # 2026-07-21: ручний прохід приніс 623 товари Allo при 30 «незібраних» задачах.
    # Беремо саме НЕ орендовану задачу: нижче ще перевіряється бекоф на тій, яку
    # щойно видала оренда, і скидати її стан звідси означало б зламати чужу перевірку
    # (так і сталось: collect/fail почав повертати 409).
    with psycopg.connect(URL, autocommit=True) as c:
        moyo_url = c.execute(
            "SELECT url FROM collect_task WHERE source='Moyo' AND leased_by IS NULL "
            "ORDER BY task_id LIMIT 1").fetchone()[0]
        c.execute("UPDATE collect_task SET last_done_at = NULL, last_status = NULL "
                  "WHERE source='Moyo' AND url = %s", (moyo_url,))
    nr = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Moyo", "url": moyo_url, "html": _cas("moyo_listing.html")})
    checks.append(("ingest/html БЕЗ task_id теж закриває задачу (ручний прохід)",
                   nr.status_code == 200 and nr.json().get("task_closed") is True, nr.json()))
    with psycopg.connect(URL, autocommit=True) as c:
        done = c.execute("SELECT last_done_at IS NOT NULL, last_status FROM collect_task "
                         "WHERE source='Moyo' AND url=%s", (moyo_url,)).fetchone()
    checks.append(("після ручного проходу задача має час і статус ok",
                   done[0] is True and done[1] == "ok", done))
    # чужа орендована задача не закривається побічно — інакше два колектори збивали б
    # одне одному розклад
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE collect_task SET leased_by='other-phone', "
                  "leased_until = now() + interval '5 minutes', last_done_at = NULL "
                  "WHERE source='Moyo' AND url=%s", (moyo_url,))
    nr2 = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Moyo", "url": moyo_url, "html": _cas("moyo_listing.html")})
    checks.append(("задачу, орендовану іншим колектором, не чіпаємо",
                   nr2.json().get("task_closed") is False, nr2.json()))

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

    # ── здоров'я збору: тиха зупинка мусить бути ВИДНОЮ ──────────────────────────
    # 2026-07-21 колектор стояв дві години, і помітили це випадково. Профіль доти
    # показував лічильник самого пристрою, який мовчить однаково і при справному
    # зборі, і при мертвому.
    checks.append(("collect/health простому юзеру → 401",
                   client.get("/api/collect/health", headers=ahdr).status_code == 401, None))
    h = client.get("/api/collect/health", headers=chdr).json()
    checks.append(("health: щойно збирали → ok",
                   h.get("ok") is True and h.get("silent_min") is not None
                   and h["silent_min"] <= h["silent_limit_min"], h))
    checks.append(("health несе числа черги",
                   h.get("tasks_total", 0) > 0 and "tasks_done_1h" in h
                   and "failing" in h and "overdue" in h, h))

    # відсуваємо ОСТАННІЙ збір за поріг — показник мусить це побачити
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE collect_task SET last_done_at = now() - interval '5 hours' "
                  "WHERE last_done_at IS NOT NULL")
    h2 = client.get("/api/collect/health", headers=chdr).json()
    checks.append(("health: тиша понад поріг → not ok + пояснення",
                   h2.get("ok") is False and "мовчить" in (h2.get("note") or ""), h2))
    checks.append(("health рахує хвилини тиші (≈300)",
                   280 <= (h2.get("silent_min") or 0) <= 320, h2.get("silent_min")))

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

    # ── «дешевше в іншій крамниці» ────────────────────────────────────────────────
    # Фікстур уже готовий вище: Allo продає A37 ЗІ ЗНИЖКОЮ, Foxtrot — той самий MPN
    # дешевше (1 999 900) і БЕЗ знижки. Представника групи обирає «знижкова
    # пріоритетно, тоді найдешевша», тож у стрічці стоїть дорожча Allo — рівно той
    # випадок, який бейдж мусить викрити.
    ch = client.get("/api/products?q=SM-A376BDGGEUC&only_discounts=1").json()
    checks.append(("картку групи веде знижкова (дорожча) Allo",
                   len(ch) == 1 and ch[0]["store"] == "Allo", ch))
    checks.append(("бейдж називає крамницю і ціну (Foxtrot, 1 999 900)",
                   len(ch) == 1 and ch[0].get("cheaper_store") == "Foxtrot"
                   and ch[0].get("cheaper_kop") == 1999900, ch))
    # РЕГРЕСІЯ, заради якої фільтри розділені на базові й звужувальні: Foxtrot-пропозиція
    # знижки НЕ має. Якби мінімум по групі рахувався ПІСЛЯ only_discounts (а це режим
    # гортання за замовчуванням), кандидата не було б видно й бейдж не спрацював би НІ РАЗУ.
    checks.append(("кандидат без знижки видно і при only_discounts=1 (інакше бейдж мертвий)",
                   len(ch) == 1 and ch[0].get("cheaper_kop") is not None
                   and ch[0].get("cheaper_kop") < ch[0]["current_kop"], ch))

    # Уцінка — ІНШИЙ стан товару, а не «те саме дешевше». Кладемо в ту саму групу
    # найдешевшу уцінену пропозицію: бейдж мусить і далі вказувати на Foxtrot.
    client.post("/api/ingest", headers=ing_tok, json={"source": "Moyo", "items": [
        {"external_ref": "/ua/samsung-a37-ucinka.html",
         "url": "https://www.moyo.ua/ua/samsung-a37-ucinka.html",
         "title": "УЦІНКА Samsung Galaxy A37 5G 8/256GB (SM-A376BDGGEUC)",
         "price_now_kop": 1500000}]})
    ch2 = client.get("/api/products?q=SM-A376BDGGEUC&only_discounts=1").json()
    checks.append(("уцінена пропозиція НЕ стає підставою для «дешевше» (лишається Foxtrot)",
                   len(ch2) == 1 and ch2[0].get("cheaper_store") == "Foxtrot"
                   and ch2[0].get("cheaper_kop") == 1999900, ch2))

    # Дешевший варіант у ТІЙ САМІЙ крамниці — не «інша крамниця»: OPPO CPH2801 —
    # два кольори одного Foxtrot з родовим артикулом, іншої крамниці в групі немає.
    op = client.get("/api/products?q=CPH2801").json()
    checks.append(("та сама крамниця не вважається «іншою» → бейджа нема",
                   len(op) >= 1 and all(d.get("cheaper_kop") is None for d in op), op))
    # товар без MPN (зоо) — групи нема, порівнювати нема з чим
    rl = client.get("/api/products?q=Royal").json()
    checks.append(("товар без MPN → бейджа нема",
                   len(rl) >= 1 and all(d.get("cheaper_kop") is None for d in rl), rl))

    # ── «Де купити»: уцінка позначена і не підміняє чисту ціну крамниці ───────────
    # Заміряно на проді 2026-07-21: із 10 груп, де поруч є уцінений і чистий товар,
    # у 8 уцінений НАЙДЕШЕВШИЙ — тобто без поділу він щоразу ставав би першим рядком
    # і читався як «найкраща ціна».
    client.post("/api/ingest", headers=ing_tok, json={"source": "Rozetka", "items": [
        {"external_ref": "/ua/off-clean/p1", "url": "https://rozetka.com.ua/ua/off-clean/p1/",
         "title": "Ноутбук OFFTEST Pro (SM-OFFTESTPRO)", "price_now_kop": 3000000}]})
    # ТА САМА крамниця має і уцінений, дешевший — у списку має лишитись ЧИСТИЙ
    client.post("/api/ingest", headers=ing_tok, json={"source": "Rozetka", "items": [
        {"external_ref": "/ua/off-used/p2", "url": "https://rozetka.com.ua/ua/off-used/p2/",
         "title": "УЦІНКА Ноутбук OFFTEST Pro (SM-OFFTESTPRO)", "price_now_kop": 2000000}]})
    # інша крамниця, де є ЛИШЕ уцінений — має бути видно, але з прапорцем
    client.post("/api/ingest", headers=ing_tok, json={"source": "Foxtrot", "items": [
        {"external_ref": "/ua/shop/off-used-only.html",
         "url": "https://www.foxtrot.com.ua/ua/shop/off-used-only.html",
         "title": "УЦІНКА Ноутбук OFFTEST Pro (SM-OFFTESTPRO)", "price_now_kop": 2500000}]})

    off_card = client.get("/api/products?q=OFFTESTPRO").json()
    checks.append(("картку веде чиста пропозиція",
                   len(off_card) == 1 and "УЦІНКА" not in off_card[0]["title"], off_card))
    offs = client.get(f"/api/product/{off_card[0]['store_product_id']}/offers").json()
    rz = next((o for o in offs if o["store"] == "Rozetka"), None)
    fx = next((o for o in offs if o["store"] == "Foxtrot"), None)
    checks.append(("крамниця з обома показує ЧИСТУ ціну, не уцінену",
                   rz is not None and rz["current_kop"] == 3000000 and rz["is_used"] is False, rz))
    checks.append(("крамниця лише з уціненим — видно, але позначено",
                   fx is not None and fx["is_used"] is True, fx))
    checks.append(("уцінене не ховаємо: обидві крамниці в списку", len(offs) == 2, offs))

    # ── уцінка не представляє групу, поки в ній є чиста пропозиція ────────────────
    # Пастка навмисна: уцінений ДЕШЕВШИЙ і ще й зі знижкою, тобто за старим порядком
    # («знижкова пріоритетно, тоді найдешевша») він гарантовано очолив би картку — і
    # віддав би їй свою назву, фото й ціну. Так на проді «УЦІНКА Телевізор LG
    # 50UA75006LA — від 16 999 ₴» представляла групу, де 8 крамниць продають новий.
    client.post("/api/ingest", headers=ing_tok, json={"source": "Rozetka", "items": [
        {"external_ref": "/ua/used-rep/p1", "url": "https://rozetka.com.ua/ua/used-rep/p1/",
         "title": "УЦІНКА Ноутбук USEDREP Test (SM-USEDREPTEST)",
         "price_now_kop": 1000000, "price_old_kop": 2000000}]})
    client.post("/api/ingest", headers=ing_tok, json={"source": "Foxtrot", "items": [
        {"external_ref": "/ua/shop/used-rep.html",
         "url": "https://www.foxtrot.com.ua/ua/shop/used-rep.html",
         "title": "Ноутбук USEDREP Test (SM-USEDREPTEST)", "price_now_kop": 1500000}]})
    rep = client.get("/api/products?q=USEDREPTEST").json()
    checks.append(("групу представляє чиста пропозиція, не уцінена",
                   len(rep) == 1 and rep[0]["store"] == "Foxtrot"
                   and "УЦІНКА" not in rep[0]["title"], rep))
    checks.append(("ціна картки — за новий товар, не за уцінений",
                   len(rep) == 1 and rep[0]["current_kop"] == 1500000, rep))

    # ── фото плитки категорії: обличчям не може бути уцінка/комплект ──────────────
    # Знижка −89% навмисне найбільша в базі: за СТАРИМ правилом («найбільша знижка»)
    # саме вона очолила б плитку. Так 2026-07-21 і сталось на проді — категорію
    # «Телевізори» представляв уцінений Samsung.
    client.post("/api/ingest", headers=ing_tok, json={"source": "Rozetka", "items": [
        {"external_ref": "/ua/tile-ucinka/p9", "url": "https://rozetka.com.ua/ua/tile-ucinka/p9/",
         "title": "УЦІНКА Смартфон TILE Test (SM-TILEUCINKA)",
         "price_now_kop": 100000, "price_old_kop": 900000,
         "image_url": "https://content.rozetka.com.ua/goods/images/big_tile/ucinka-tile.jpg"}]})
    cats_t = client.get("/api/categories").json()
    bad_tile = [c["slug"] for c in cats_t if (c.get("image_url") or "").find("ucinka-tile") >= 0]
    checks.append(("уцінений товар не стає обличчям категорії", bad_tile == [], bad_tile))
    checks.append(("плитки далі мають фото (правило не лишило їх порожніми)",
                   any(c.get("image_url") for c in cats_t),
                   [(c["slug"], bool(c.get("image_url"))) for c in cats_t[:4]]))
    # лічильник не залежить від того, чи знайшлось фото
    checks.append(("лічильник категорій не змінився через фільтр фото",
                   all(c["n"] >= 1 for c in cats_t), [(c["slug"], c["n"]) for c in cats_t[:4]]))

    # ── «знижка нічого не дає»: гучна знижка при ринковій ціні ────────────────────
    # Сіємо еталонний випадок Moyo/ASUS: три крамниці тримають ОДНАКОВУ ціну, і лише
    # одна вбирає її в «−56%» від вигаданої старої. Ціни рівні → бейдж «дешевше в
    # іншій крамниці» тут не спрацює, і без цього сигналу ми б мовчали.
    for src, ref, title, now_kop, old_kop in (
            ("Rozetka", "/ua/hollow-a/p1", "Ноутбук HOLLOW TestBook (SM-HOLLOWTEST)", 5000000, 11000000),
            ("Foxtrot", "/ua/shop/hollow-b.html", "Ноутбук HOLLOW TestBook (SM-HOLLOWTEST)", 5000000, None),
            ("Moyo", "/ua/hollow-c.html", "Ноутбук HOLLOW TestBook (SM-HOLLOWTEST)", 5000000, None)):
        host = {"Rozetka": "https://rozetka.com.ua", "Foxtrot": "https://www.foxtrot.com.ua",
                "Moyo": "https://www.moyo.ua"}[src]
        item = {"external_ref": ref, "url": host + ref, "title": title, "price_now_kop": now_kop}
        if old_kop:
            item["price_old_kop"] = old_kop
        client.post("/api/ingest", headers=ing_tok, json={"source": src, "items": [item]})

    hol = client.get("/api/products?q=HOLLOWTEST&only_discounts=1").json()
    checks.append(("картку веде знижкова Rozetka (−55%)",
                   len(hol) == 1 and hol[0]["store"] == "Rozetka", hol))
    checks.append(("сигнал рахує 2 крамниці з тією самою ціною без знижки",
                   len(hol) == 1 and hol[0].get("same_price_n") == 2, hol))
    # ціни рівні → «дешевше в іншій крамниці» мовчить; саме тому потрібен окремий сигнал
    checks.append(("при рівних цінах бейдж «дешевше» не спрацьовує",
                   len(hol) == 1 and hol[0].get("cheaper_kop") is None, hol))

    # Конкурент, який САМ заявляє знижку, кандидатом не є: коли знижку оголосили всі,
    # це загальне зниження РРЦ, а не накачування однієї крамниці.
    client.post("/api/ingest", headers=ing_tok, json={"source": "Allo", "items": [
        {"external_ref": "/ua/hollow-d", "url": "https://allo.ua/ua/hollow-d",
         "title": "Ноутбук HOLLOW TestBook (SM-HOLLOWTEST)",
         "price_now_kop": 5000000, "price_old_kop": 9000000}]})
    hol2 = client.get("/api/products?q=HOLLOWTEST&only_discounts=1").json()
    checks.append(("крамниця зі своєю знижкою не рахується (лишилось 2)",
                   len(hol2) == 1 and hol2[0].get("same_price_n") == 2, hol2))

    # А39 (звичайний товар) поріг не проходить — знижка тиха
    quiet = client.get("/api/products?q=SM-A376BDGGEUC&only_discounts=1").json()
    checks.append(("тиха знижка сигналу не піднімає",
                   len(quiet) == 1 and quiet[0].get("same_price_n") is None, quiet))

    # сортування «де дешевше»: бейджеві картки нагору, від найбільшої різниці.
    # Без нього сигнал (1.8% карток) практично не зустрічається під час гортання.
    srt = client.get("/api/products?sort=cheaper").json()
    with_ch = [x for x in srt if x.get("cheaper_kop")]
    checks.append(("sort=cheaper: картки з дешевшим поруч — на початку",
                   len(with_ch) >= 1 and srt[0].get("cheaper_kop") is not None,
                   [bool(x.get("cheaper_kop")) for x in srt[:5]]))
    checks.append(("sort=cheaper: різниця спадає",
                   all((with_ch[i]["current_kop"] - with_ch[i]["cheaper_kop"])
                       >= (with_ch[i+1]["current_kop"] - with_ch[i+1]["cheaper_kop"])
                       for i in range(len(with_ch) - 1)),
                   [x["current_kop"] - x["cheaper_kop"] for x in with_ch]))
    # сортування НЕ фільтр: решта каталогу лишається доступною (інакше в смартфонах,
    # де таких карток нема взагалі, екран був би глухим кутом)
    checks.append(("sort=cheaper не відрізає решту каталогу",
                   len(srt) > len(with_ch), (len(srt), len(with_ch))))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
