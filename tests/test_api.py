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
from api import db as _qdb                              # noqa: E402  (константи + db-рівневі перевірки)
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

    def signup(email, password):
        """Реєстрація більше НЕ повертає токен: відповідь однакова для нової й наявної
        адреси (інакше 409 сам був би оракулом «чи є акаунт»). Сесію беремо звичайним
        входом — тим самим паролем, який щойно ввели.

        Ліміт реєстрацій знімаємо: TestClient шле все з однієї адреси, а REGISTER_LIMIT
        це 5/год/IP — службові акаунти тесту впирались би в нього й мовчки не
        створювались (саме на цьому впав CI 2026-07-27)."""
        from api import ratelimit as _r
        _r.register_limiter._hits.clear()
        r = client.post("/api/auth/register", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return client.post("/api/auth/login",
                           json={"email": email, "password": password}).json()

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

    # ── S14: порівняння side-by-side ─────────────────────────────────────────────
    spid2 = disc[1]["store_product_id"]
    checks.append(("compare <2 → 400",
                   client.get(f"/api/compare?ids={spid}").status_code == 400, None))
    checks.append(("compare >4 → 400",
                   client.get("/api/compare?ids=1,2,3,4,5").status_code == 400, None))
    checks.append(("compare не-int → 400",
                   client.get("/api/compare?ids=1,abc").status_code == 400, None))
    cmp = client.get(f"/api/compare?ids={spid},{spid2}").json()
    checks.append(("compare: 2 товари в порядку ids",
                   len(cmp["products"]) == 2
                   and [p["store_product_id"] for p in cmp["products"]] == [spid, spid2],
                   [p["store_product_id"] for p in cmp["products"]]))
    checks.append(("compare: базові факти (title/ціна/бейдж/offers_n)",
                   all(k in cmp["products"][0] for k in
                       ("title", "price_kop", "badge_state", "offers_n")), cmp["products"][0]))
    checks.append(("compare: spec_rows вирівняні по колонках (2)",
                   all(len(r["values"]) == 2 for r in cmp["spec_rows"]), None))

    cats = client.get("/api/categories").json()
    checks.append(("категорії з активними знижками (koty-suhyi-korm)",
                   any(c["slug"] == "koty-suhyi-korm" and c["n"] > 0 for c in cats), cats))
    # сітка-каталог (§17): кожна категорія несе розділ + іконку + поле фото-представника
    checks.append(("категорії несуть section+icon",
                   all(c.get("section") and c.get("icon") for c in cats), cats))
    checks.append(("категорії несуть image_url (фото плитки; може бути null)",
                   all("image_url" in c for c in cats), [list(c) for c in cats[:2]]))
    # цінові межі фільтра (§17-nav): ключі є завжди; значення або null (замало
    # даних, n<12), або пара «гарних» меж lo<hi
    checks.append(("категорії несуть p33_kop/p66_kop (null або lo<hi)",
                   all("p33_kop" in c and "p66_kop" in c
                       and ((c["p33_kop"] is None and c["p66_kop"] is None)
                            or (isinstance(c["p33_kop"], int) and isinstance(c["p66_kop"], int)
                                and c["p33_kop"] < c["p66_kop"]))
                       for c in cats),
                   [(c["slug"], c["p33_kop"], c["p66_kop"]) for c in cats[:4]]))
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
    # rate-лімітери — module-level singletons, а TestClient шле все з одного IP;
    # скидаємо стан, щоб численні auth-запити тесту не впіймали 429 (S13)
    from api import ratelimit as _rl
    for _lim in (_rl.login_limiter, _rl.register_limiter, _rl.email_limiter, _rl.code_limiter):
        _lim._hits.clear()
    reg = client.post("/api/auth/register", json={"email": "Test@Hapay.today", "password": "supersecret"})
    checks.append(("register 200 без токена (сесію не віддаємо)",
                   reg.status_code == 200 and reg.json() == {"sent": True}, reg.json()))
    tok = client.post("/api/auth/login",
                      json={"email": "test@hapay.today",
                            "password": "supersecret"}).json().get("token", "")
    ahdr = {"Authorization": f"Bearer {tok}"}
    checks.append(("акаунт справді створено (вхід працює)", bool(tok), None))

    # ⚠ Головне тут: відповідь на ДУБЛЬ і на НОВУ адресу нерозрізненна — інакше
    # будь-хто перевіряв би, чи є в нас акаунт на чужу пошту (T20, переглянуто 27.07).
    dup = client.post("/api/auth/register",
                      json={"email": "test@hapay.today", "password": "another1"})
    fresh = client.post("/api/auth/register",
                        json={"email": "brand-new-2026@hapay.today", "password": "another1"})
    checks.append(("дубль і нова адреса — ОДНАКОВІ код і тіло",
                   dup.status_code == fresh.status_code == 200
                   and dup.json() == fresh.json() == {"sent": True},
                   (dup.status_code, dup.json(), fresh.status_code, fresh.json())))
    checks.append(("дубль НЕ створив другого акаунта",
                   client.post("/api/auth/login",
                               json={"email": "test@hapay.today",
                                     "password": "another1"}).status_code == 401, None))
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

    # ── S13: верифікація email + скидання пароля ─────────────────────────────────
    from api import auth as _qa
    checks.append(("новий акаунт: email_verified=false",
                   mer.get("email_verified") is False, mer.get("email_verified")))
    uid = int(mer["user_id"])
    # код іде в лист (у БД лише хеш) — тест вставляє ВІДОМИЙ код прямо, щоб перевірити
    # consume-логіку ендпойнтів, не заглядаючи в пошту
    def _put_code(kind, code, secs=600):
        with psycopg.connect(URL, autocommit=True) as c:
            c.execute("UPDATE account_token SET used_at=now() WHERE user_id=%s AND kind=%s "
                      "AND used_at IS NULL", (uid, kind))
            c.execute("INSERT INTO account_token (user_id,kind,code_hash,expires_at) "
                      "VALUES (%s,%s,%s, now()+make_interval(secs=>%s))",
                      (uid, kind, _qa.hash_code(code), secs))

    checks.append(("verify без коду → 400",
                   client.post("/api/auth/verify", json={}, headers=ahdr).status_code == 400, None))
    checks.append(("verify з чужим кодом → 400",
                   client.post("/api/auth/verify", json={"code": "000000"},
                               headers=ahdr).status_code == 400, None))
    _put_code("verify", "424242")
    vr = client.post("/api/auth/verify", json={"code": "424242"}, headers=ahdr)
    checks.append(("verify правильним кодом → email_verified=true",
                   vr.status_code == 200 and vr.json().get("email_verified") is True, vr.json()))
    checks.append(("/api/me тепер verified", client.get("/api/me", headers=ahdr).json()
                   .get("email_verified") is True, None))
    checks.append(("той самий код вдруге → 400 (одноразовий)",
                   client.post("/api/auth/verify", json={"code": "424242"},
                               headers=ahdr).status_code == 400, None))
    # протухлий код
    _put_code("verify", "111111", secs=-10)
    checks.append(("протермінований код → 400",
                   client.post("/api/auth/verify", json={"code": "111111"},
                               headers=ahdr).status_code == 400, None))

    # ── перебір коду: промахи ВИТРАЧАЮТЬ сам код, не лише IP-квоту ───────────────
    # Ревʼю 2026-07-26: ліміт стояв тільки на IP, тож перебір 6-значного коду
    # масштабувався разом із числом адрес у зловмисника. Тепер код гасне після
    # MAX_CODE_ATTEMPTS промахів — байдуже, звідки їх робили.
    _put_code("verify", "999111")
    for _lim in (_rl.code_limiter,):
        _lim._hits.clear()
    codes_wrong = [f"{i:06d}" for i in range(_qdb.MAX_CODE_ATTEMPTS)]
    for c in codes_wrong:
        _rl.code_limiter._hits.clear()          # знімаємо IP-квоту — перевіряємо САМЕ лічильник коду
        client.post("/api/auth/verify", json={"code": c}, headers=ahdr)
    # Стан БД перевіряємо ДО спроби правильним кодом: успішний verify сам ставить
    # used_at, тож після нього ця перевірка проходила б із хибної причини.
    with psycopg.connect(URL) as c:
        att, used = c.execute(
            "SELECT attempts, used_at IS NOT NULL FROM account_token "
            "WHERE user_id=%s AND kind='verify' ORDER BY created_at DESC LIMIT 1",
            (uid,)).fetchone()
    checks.append((f"промахи ЗЛІЧЕНО на самому коді (attempts={_qdb.MAX_CODE_ATTEMPTS})",
                   att == _qdb.MAX_CODE_ATTEMPTS, att))
    checks.append(("код погашено після ліміту промахів", used is True, used))
    _rl.code_limiter._hits.clear()
    burned = client.post("/api/auth/verify", json={"code": "999111"}, headers=ahdr)
    checks.append((f"код гасне після {_qdb.MAX_CODE_ATTEMPTS} промахів (правильний уже не діє)",
                   burned.status_code == 400, burned.status_code))
    # свіжий код після цього працює — гасне КОД, а не акаунт
    _put_code("verify", "424243")
    _rl.code_limiter._hits.clear()
    ok_after = client.post("/api/auth/verify", json={"code": "424243"}, headers=ahdr)
    checks.append(("новий код після згаслого працює (блокуємо код, не людину)",
                   ok_after.status_code == 200, ok_after.status_code))

    # reset: no-enumeration (неіснуючий email — теж 200) + повний цикл
    checks.append(("reset/request неіснуючого email → 200 (не розкриваємо)",
                   client.post("/api/auth/reset/request",
                               json={"email": "nobody@hapay.today"}).status_code == 200, None))
    rr = client.post("/api/auth/reset/request", json={"email": "test@hapay.today"})
    checks.append(("reset/request існуючого → 200", rr.status_code == 200, rr.status_code))
    _put_code("reset", "775533")
    checks.append(("reset/confirm короткий пароль → 400",
                   client.post("/api/auth/reset/confirm",
                               json={"email": "test@hapay.today", "code": "775533",
                                     "new_password": "short"}).status_code == 400, None))
    rc = client.post("/api/auth/reset/confirm",
                     json={"email": "test@hapay.today", "code": "775533",
                           "new_password": "brandnewpass"})
    checks.append(("reset/confirm правильним кодом → 200", rc.status_code == 200, rc.json()))
    checks.append(("вхід НОВИМ паролем → 200",
                   client.post("/api/auth/login",
                               json={"email": "test@hapay.today",
                                     "password": "brandnewpass"}).status_code == 200, None))
    checks.append(("вхід СТАРИМ паролем → 401",
                   client.post("/api/auth/login",
                               json={"email": "test@hapay.today",
                                     "password": "supersecret"}).status_code == 401, None))
    checks.append(("reset-код після зміни пароля мертвий → 400",
                   client.post("/api/auth/reset/confirm",
                               json={"email": "test@hapay.today", "code": "775533",
                                     "new_password": "yetanother1"}).status_code == 400, None))
    # відновлюємо пароль для решти тесту (нижче login під supersecret не потрібен, але
    # ahdr-токен лишається валідним — JWT не залежить від пароля)

    # ⚠ ЗМІНА КОНТРАКТУ (S29): стеження за запитом тепер ВИМАГАЄ цільову ціну.
    # Раніше такий запис створювався, але сповіщати по ньому не було чим — «повідом про
    # будь-яке зниження серед усього, що підходить під слово» це розсилка, а не
    # сповіщення. Клієнтів це не зачепило: kind='query' не створював ЖОДЕН із них
    # (перевірено пошуком по web/ і app-maui/ перед зміною).
    checks.append(("query без цілі → 400 (свідома зміна контракту)",
                   client.post("/api/me/watchlist", json={"kind": "query", "query_text": "iphone"},
                               headers=ahdr).status_code == 400, None))
    wa = client.post("/api/me/watchlist", headers=ahdr,
                     json={"kind": "query", "query_text": "iphone", "target_kop": 5000000})
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

    # ── стеження за КАТЕГОРІЄЮ: новини + ack (0165) ──────────────────────────────
    with psycopg.connect(URL) as c:
        cslug, = c.execute(
            "SELECT c.slug FROM category c JOIN store_product sp "
            "ON sp.category_id = c.category_id WHERE sp.store_product_id = %s",
            (spid,)).fetchone()
    wc = client.post("/api/me/watchlist",
                     json={"kind": "category", "query_text": cslug}, headers=ahdr)
    checks.append(("watch категорії → 200", wc.status_code == 200, wc.json()))
    wc2 = client.post("/api/me/watchlist",
                      json={"kind": "category", "query_text": cslug}, headers=ahdr)
    checks.append(("повторний watch категорії не дублює",
                   wc2.json().get("watchlist_id") == wc.json().get("watchlist_id"),
                   (wc.json(), wc2.json())))
    checks.append(("категорія видна у списку стеження з людською назвою",
                   any(x["kind"] == "category" and x["query_text"] == cslug and x["title"]
                       for x in client.get("/api/me/watchlist", headers=ahdr).json()), None))
    # події категорії старіші за момент підписки → новин нема
    checks.append(("щойно підписався → новин ще нема",
                   client.get("/api/me/watchlist/category-news", headers=ahdr).json() == [],
                   None))
    # пересуваємо водяний знак у минуле — наявні події стають «новими»
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE watchlist SET created_at = created_at - interval '2 days' "
                  "WHERE watchlist_id = %s", (wc.json()["watchlist_id"],))
    cn = client.get("/api/me/watchlist/category-news", headers=ahdr).json()
    checks.append(("нові знижки категорії згруповано одним рядком",
                   len(cn) == 1 and cn[0]["new_n"] >= 1 and cn[0]["slug"] == cslug
                   and cn[0]["category"] and cn[0]["top_title"], cn))
    ackc = client.post("/api/me/watchlist/category-news/ack", headers=ahdr,
                       json={"watchlist_ids": [cn[0]["watchlist_id"]]})
    checks.append(("ack категорійних новин → 1", ackc.json().get("acked") == 1, ackc.json()))
    checks.append(("після ack ті самі знижки не турбують",
                   client.get("/api/me/watchlist/category-news", headers=ahdr).json() == [],
                   None))

    # ── фільтр «лише підтверджені» у стрічці ─────────────────────────────────────
    vb = client.get("/api/products?badge=verified")
    checks.append(("badge=verified → 200 і лише verified/provisional",
                   vb.status_code == 200 and all(
                       r["badge_state"] in ("verified", "verified_provisional")
                       for r in vb.json()), [r.get("badge_state") for r in vb.json()[:5]]))

    # ── фільтр «завищена стара ціна» + валідація бейджа ──────────────────────────
    # ⚠ Було: `if badge == "verified"` — БУДЬ-ЯКЕ інше значення мовчки ігнорувалось,
    # тобто ?badge=pumped віддавав повний каталог, ніби фільтр застосовано (2026-07-26).
    pb = client.get("/api/products?badge=pumped")
    checks.append(("badge=pumped → 200 і лише pumped (не весь каталог)",
                   pb.status_code == 200
                   and all(r["badge_state"] == "pumped" for r in pb.json()),
                   [r.get("badge_state") for r in pb.json()[:5]]))
    allp = client.get("/api/products").json()
    checks.append(("badge=pumped справді ЗВУЖУЄ (не дорівнює нефільтрованому)",
                   len(pb.json()) < len(allp) or len(allp) == 0, (len(pb.json()), len(allp))))
    checks.append(("невідомий бейдж → 400, не тиша (/products)",
                   client.get("/api/products?badge=zzz").status_code == 400, None))
    checks.append(("невідомий бейдж → 400, не тиша (/discounts)",
                   client.get("/api/discounts?badge=zzz").status_code == 400, None))
    dv = client.get("/api/discounts?badge=verified")
    checks.append(("/discounts?badge=verified тягне й provisional",
                   dv.status_code == 200 and all(
                       d["badge_state"] in ("verified", "verified_provisional")
                       for d in dv.json()), [d.get("badge_state") for d in dv.json()[:5]]))

    # ── S19: картка товару для сторінки /product/{id} ────────────────────────────
    # /offers навмисно бідний (крамниця+ціна+URL) — сторінці потрібні фото, бейдж і
    # 30-денна база, інакше головне твердження продукту на ній просто відсутнє.
    cd = client.get(f"/api/product/{spid}/card")
    cj = cd.json()
    checks.append(("/card повертає повну картку (фото/бейдж/база/категорія)",
                   cd.status_code == 200 and all(k in cj for k in
                       ("title", "url", "image_url", "store", "current_kop",
                        "badge_state", "reference_kop", "category_slug", "group_stores")),
                   sorted(cj) if cd.status_code == 200 else cd.status_code))
    checks.append(("/card: назва й крамниця не порожні",
                   bool(cj.get("title")) and bool(cj.get("store")),
                   (cj.get("title"), cj.get("store"))))
    checks.append(("/card неіснуючого товару → 404",
                   client.get("/api/product/99999999/card").status_code == 404, None))
    # товар БЕЗ активної знижки теж має сторінку (на неї ведуть стеження) — ціну
    # тоді беремо з останнього снапшота, а не віддаємо порожнечу
    with psycopg.connect(URL) as c:
        plain = c.execute(
            "SELECT sp.store_product_id FROM store_product sp "
            "LEFT JOIN discount_event de ON de.store_product_id = sp.store_product_id "
            "  AND de.ended_at IS NULL WHERE de.discount_event_id IS NULL LIMIT 1").fetchone()
    if plain:
        pc = client.get(f"/api/product/{plain[0]}/card").json()
        checks.append(("/card товару без знижки → ціна з останнього снапшота",
                       pc.get("current_kop") is not None and pc.get("badge_state") is None,
                       (pc.get("current_kop"), pc.get("badge_state"))))

    # ── S19: сторінки сайту віддаються, catch-all не зламано ─────────────────────
    for path in ("/", "/catalog", "/login", "/me", f"/product/{spid}"):
        r = client.get(path)
        checks.append((f"сторінка {path} → 200 html",
                       r.status_code == 200 and "text/html" in r.headers.get("content-type", ""),
                       r.status_code))
    for a in ("app.css", "app.js", "catalog.js"):
        r = client.get(f"/s/{a}")
        checks.append((f"/s/{a} віддається",
                       r.status_code == 200 and len(r.text) > 100, r.status_code))
    checks.append(("/s/ поза білим списком → 404 (без обходу шляхом)",
                   client.get("/s/../api/main.py").status_code in (404, 400), None))
    checks.append(("юр-сторінки цілі після додавання маршрутів",
                   client.get("/privacy").status_code == 200, None))
    checks.append(("невідомий шлях → 404", client.get("/nema-takoyi").status_code == 404, None))

    # ── фільтр за РОЗДІЛОМ (набір категорій; у БД розділу нема — мапа в taxonomy) ──
    # Знайдено оператором: посилання розділів на головній вели просто в /catalog,
    # бо фільтра за розділом не існувало.
    from taxonomy import slugs_in_section as _sis
    sect_of_cat = next((s for s in ("Зоотовари", "Електроніка", "Інше")
                        if cslug in _sis(s)), None)
    if sect_of_cat:
        sd = client.get(f"/api/discounts?section={sect_of_cat}")
        checks.append((f"фільтр section={sect_of_cat} → 200 і не порожньо",
                       sd.status_code == 200 and len(sd.json()) >= 1, len(sd.json())))
        checks.append(("розділ ширший за категорію (містить її товари)",
                       len(sd.json()) >= len(client.get(
                           f"/api/discounts?category={cslug}").json()), None))
    checks.append(("невідомий розділ → 400, не порожня видача",
                   client.get("/api/discounts?section=Нема-такого").status_code == 400, None))
    checks.append(("невідомий розділ і в /products → 400",
                   client.get("/api/products?section=Нема-такого").status_code == 400, None))
    # категорія має пріоритет над розділом: разом вони дали б перетин, якого не просили
    both = client.get(f"/api/discounts?category={cslug}&section=Електроніка")
    only = client.get(f"/api/discounts?category={cslug}")
    checks.append(("категорія переважає розділ (перетину не робимо)",
                   both.status_code == 200 and len(both.json()) == len(only.json()),
                   (len(both.json()), len(only.json()))))

    # ── свіжість даних (шапка стрічки) ───────────────────────────────────────────
    fr = client.get("/api/freshness")
    checks.append(("/api/freshness публічний і віддає minutes",
                   fr.status_code == 200 and "minutes" in fr.json(), fr.json()))

    # чуже стеження не видаляється — інакше будь-хто чистив би чужі списки
    other = signup("watcher2@hapay.today", "watchpass")
    ohdr = {"Authorization": f"Bearer {other.get('token', '')}"}
    checks.append(("чужий запис стеження не видаляється → 404",
                   client.delete(f"/api/me/watchlist/{wit['watchlist_id']}",
                                 headers=ohdr).status_code == 404, None))
    checks.append(("свій запис видаляється → 200",
                   client.delete(f"/api/me/watchlist/{wit['watchlist_id']}",
                                 headers=ahdr).status_code == 200, None))

    # ── html-ingest (S11 етап 3): гейт ролі collector + сервер парсить переслане HTML ──
    # ролі роздає власник напряму в БД (trusted-people) — робимо акаунт колектором
    _rl.register_limiter._hits.clear()          # див. signup(): ліміт 5/год/IP
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

    # ── HTML-шлях мусить ЗБЕРЕГТИ gtins (регресія 2026-07-22) ──────────────────────
    # Реальний збір іде саме HTML-шляхом: adapter.extract → dataclasses.asdict → validate.
    # asdict лишає поле-tuple ТУПЛОМ, а validate_item перевіряв лише `isinstance(list)` →
    # губив УСІ штрихкоди. На проді Подорожник зібрав 58 товарів із 0 gtin, хоча адаптер
    # брав 60/60. JSON-шлях (/api/ingest) баг маскував — там gtins приходить списком.
    # Тому перевірка мусить іти саме через /api/ingest/html, як цей тест.
    pr = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Podorozhnyk", "url": "https://podorozhnyk.ua/vitamini-ta-dobavki/",
        "html": _cas("podorozhnyk_listing.html")})
    checks.append(("ingest/html Подорожник → 2 прийнято (рецептурний пропущено)",
                   pr.status_code == 200 and pr.json().get("accepted") == 2, pr.json()))
    with psycopg.connect(URL, autocommit=True) as c:
        pg = c.execute("SELECT count(*), count(gtin), count(match_key) "
                       "FROM store_product sp JOIN source s USING (source_id) "
                       "WHERE s.name = 'Podorozhnyk'").fetchone()
    checks.append(("HTML-шлях зберіг gtin+match_key (не загубив tuple при asdict)",
                   tuple(pg) == (2, 2, 2), pg))

    # ── add.ua ДВОФАЗНИЙ (друга аптека): лістинг discover-ить товари, товар несе штрихкод ──
    # Штрихкод (ключ GTIN) add.ua дає лише на сторінці товару, тож збираємо як хаб:
    # лістинг → discover_re впізнає його → повертає URL товарів (kind=hub); товар →
    # extract → персист із GTIN зі рядка «Штрих-код» (а не з ld+json SKU).
    al = client.post("/api/ingest/html", headers=chdr, json={
        "source": "AddUa", "url": "https://www.add.ua/ua/kosmetika/",
        "html": _cas("addua_listing.html")})
    aj = al.json()
    checks.append(("add.ua лістинг → kind=hub, 3 товар-URL (discover_re)",
                   al.status_code == 200 and aj.get("kind") == "hub"
                   and len(aj.get("discovered", [])) == 3 and aj.get("accepted") == 0, aj))
    ap = client.post("/api/ingest/html", headers=chdr, json={
        "source": "AddUa",
        "url": "https://www.add.ua/ua/healix-heliks-omega-3-1000-mkg-kapsuly-90.html",
        "html": _cas("addua_product.html")})
    checks.append(("add.ua сторінка товару → 1 прийнято (extract, не discover)",
                   ap.status_code == 200 and ap.json().get("kind") == "page"
                   and ap.json().get("accepted") == 1, ap.json()))
    with psycopg.connect(URL, autocommit=True) as c:
        ag = c.execute("SELECT gtin FROM store_product sp JOIN source s USING (source_id) "
                       "WHERE s.name = 'AddUa'").fetchone()
    checks.append(("add.ua товар персиснув із GTIN зі штрихкоду (не внутрішній SKU)",
                   ag is not None and ag[0] == "04820274801259", ag))

    # ── пошук за кирилицею-фонетикою бренду (§9.1): «айфон» мусить знайти iPhone ────
    # На проді (2026-07-22): iphone → 50 товарів, айфон → 6. Українець набирає кирилицею,
    # а бренд у назві латиницею → ILIKE ANY з підстановкою (search.py). Оригінал теж
    # лишається серед патернів, тож поведінка латинських запитів не змінюється.
    client.post("/api/ingest", headers=ing_tok, json={"source": "Rozetka", "items": [
        {"external_ref": "/ua/apple-iphone-translit-test.html",
         "url": "https://rozetka.com.ua/ua/apple-iphone-translit-test.html",
         "title": "Смартфон Apple iPhone 17 Pro 256GB translit-test",
         "price_now_kop": 4999900, "price_old_kop": 5499900}]})
    cyr = client.get("/api/products?q=айфон").json()
    checks.append(("пошук «айфон» знаходить iPhone (транслітерація бренду)",
                   any("iphone" in (d.get("title", "").lower()) for d in cyr), len(cyr)))
    # контроль: латинський запит як і був — знаходить той самий товар
    lat = client.get("/api/products?q=iPhone 17 Pro 256GB translit-test").json()
    checks.append(("латинський пошук не зламався (той самий товар)",
                   any("translit-test" in d.get("title", "") for d in lat), len(lat)))

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
    # «Наш вибір» (S9): група з 1 крамниці → null (нема з чим порівнювати, guardrail §7)
    ch1 = client.get(f"/api/product/{a37_id}/choice").json()
    checks.append(("choice для групи-одиначки → null", ch1.get("choice") is None, ch1))

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
    # «Наш вибір» (S9): 2 крамниці → об'єкт зі СКЛАДНИКАМИ (пояснюваність — вимога брифа);
    # без delivery_rule ефективна = ціна + no_delivery_data=true; savings = різниця цін
    ch2 = client.get(f"/api/product/{a37_id}/choice").json().get("choice")
    checks.append(("choice для 2 крамниць: вибір + економія + складники",
                   ch2 is not None and ch2["our_choice"] == "Foxtrot"
                   and ch2["savings_kop"] == duo[1]["current_kop"] - 1999900
                   and len(ch2["candidates"]) == 2
                   and all("components" in c and "no_delivery_data" in c
                           for c in ch2["candidates"]), ch2))
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

    # ── S12: характеристики з карток — сів → card-ingest → /specs → тихий нуль ────
    from api import qtasks as qts
    with psycopg.connect(URL, autocommit=True) as c:
        a37_url, = c.execute("SELECT url FROM store_product WHERE store_product_id = %s",
                             (a37_id,)).fetchone()
        seeded = qts.seed_card_tasks(c)
        card_row = c.execute("SELECT task_id, priority FROM collect_task "
                             "WHERE kind='card' AND source='Allo' AND url=%s",
                             (a37_url,)).fetchone()
    checks.append(("seed_card_tasks: card-задача для Allo-члена групи A37 (prio 200)",
                   card_row is not None and card_row[1] == qts.CARD_PRIORITY,
                   (seeded, card_row)))
    spr = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Allo", "url": a37_url, "html": _cas("allo_card.html")})
    checks.append(("ingest/html картки → kind=card, 29 атрибутів",
                   spr.status_code == 200 and spr.json().get("kind") == "card"
                   and spr.json().get("accepted") == 29, spr.json()))
    with psycopg.connect(URL, autocommit=True) as c:
        gone = c.execute("SELECT 1 FROM collect_task WHERE kind='card' AND url=%s",
                         (a37_url,)).fetchone()
    checks.append(("card-задача одноразова: після ok видалена з черги", gone is None, gone))
    # специфікація групи віддається ІНШОМУ члену (Foxtrot): одна картка на групу
    spx = client.get(f"/api/product/{fox_off['store_product_id']}/specs").json().get("specs")
    checks.append(("/specs для Foxtrot-члена → атрибути Allo-картки з провенансом",
                   spx is not None and spx["store"] == "Allo"
                   and spx["source_url"] == a37_url and spx["collected_day"]
                   and {"name": "Тип витяжки", "value": "Телескопічна"} in spx["attrs"],
                   spx and {k: spx[k] for k in ("store", "collected_day")}))
    # «тихий нуль» card: лістинг замість картки → 0 атрибутів → fail з бекофом,
    # задача ЖИВЕ (ok видалив би її назавжди — найгірший різновид тихого нуля)
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("INSERT INTO collect_task (source, url, kind, priority, repeat_min) "
                  "VALUES ('Allo', %s, 'card', %s, 1440) ON CONFLICT DO NOTHING",
                  (a37_url, qts.CARD_PRIORITY))
    zr = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Allo", "url": a37_url, "html": _cas("allo_tv_listing.html")})
    with psycopg.connect(URL, autocommit=True) as c:
        zrow = c.execute("SELECT last_status FROM collect_task WHERE kind='card' "
                         "AND url=%s", (a37_url,)).fetchone()
    checks.append(("тихий нуль card: 0 атрибутів → fail із бекофом, задача лишилась",
                   zr.status_code == 200 and zr.json().get("kind") == "card"
                   and zr.json().get("accepted") == 0
                   and zrow is not None and zrow[0].startswith("fail:0"),
                   (zr.json(), zrow)))
    with psycopg.connect(URL, autocommit=True) as c:   # прибрати card-хвіст перед чеками черги
        c.execute("DELETE FROM collect_task WHERE kind='card'")

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
    # ── GTIN-групування (аптеки/медтовари, 2026-07-22) ────────────────────────────
    # Суть: у цих назв НЕМАЄ артикула (extract_mpn → None), тож за назвою вони НЕ
    # зійшлися б — рівно та стеля, об яку розбився матчинг для консолей/кормів (T17).
    # Але штрихкод той самий, тож match_key = GTIN зводить їх в одну групу. Дві РІЗНІ
    # назви у двох крамницях → одна картка, offers_n=2.
    GT = ["4820135261796"]              # реальний EAN-13 (валідна контрольна цифра)
    client.post("/api/ingest", headers=ing_tok, json={"source": "Foxtrot", "items": [
        {"external_ref": "/ua/shop/tonometr-microlife-a2.html",
         "url": "https://www.foxtrot.com.ua/ua/shop/tonometr-microlife-a2.html",
         "title": "Тонометр Microlife BP A2 Basic автоматичний",
         "price_now_kop": 129900, "price_old_kop": 159900, "gtins": GT}]})
    client.post("/api/ingest", headers=ing_tok, json={"source": "Moyo", "items": [
        {"external_ref": "/ua/tonometr-microlife.html",
         "url": "https://www.moyo.ua/ua/tonometr-microlife.html",
         "title": "Вимірювач тиску Microlife (автоматичний)",
         "price_now_kop": 139900, "price_old_kop": 159900, "gtins": GT}]})
    gt_card = client.get("/api/discounts?q=Microlife").json()
    checks.append(("GTIN: різні назви без артикула, той самий штрихкод → ОДНА картка",
                   len(gt_card) == 1, len(gt_card)))
    checks.append(("GTIN-група → offers_n=2 (дві крамниці за штрихкодом)",
                   bool(gt_card) and gt_card[0].get("offers_n") == 2,
                   [d.get("offers_n") for d in gt_card]))
    if gt_card:
        go = client.get(f"/api/product/{gt_card[0]['store_product_id']}/offers").json()
        checks.append(("GTIN «Де купити»: дві крамниці (Foxtrot + Moyo) за штрихкодом",
                       {o["store"] for o in go} == {"Foxtrot", "Moyo"},
                       [o.get("store") for o in go]))
    # контроль: невалідний штрихкод (бита контрольна цифра) НЕ створює групу —
    # два товари з «4820135261797» лишаються кожен сам собі (match_key від назви/None)
    client.post("/api/ingest", headers=ing_tok, json={"source": "Foxtrot", "items": [
        {"external_ref": "/ua/shop/plastyr-a.html",
         "url": "https://www.foxtrot.com.ua/ua/shop/plastyr-a.html",
         "title": "Пластир медичний А", "price_now_kop": 5000, "price_old_kop": 9000,
         "gtins": ["4820135261797"]}]})
    client.post("/api/ingest", headers=ing_tok, json={"source": "Moyo", "items": [
        {"external_ref": "/ua/plastyr-b.html",
         "url": "https://www.moyo.ua/ua/plastyr-b.html",
         "title": "Пластир медичний Б", "price_now_kop": 6000, "price_old_kop": 9000,
         "gtins": ["4820135261797"]}]})
    bad = client.get("/api/discounts?q=Пластир медичний").json()
    checks.append(("битий штрихкод не групує → 2 окремі картки, offers_n=1 кожна",
                   len(bad) == 2 and all(d.get("offers_n") == 1 for d in bad),
                   [(d.get("title"), d.get("offers_n")) for d in bad]))

    if oppo:
        oo = client.get(f"/api/product/{oppo[0]['store_product_id']}/offers").json()
        checks.append(("«Де купити»: одна пропозиція на крамницю (дедуп Foxtrot)",
                       len(oo) == 1 and oo[0]["store"] == "Foxtrot", [o["store"] for o in oo]))

    # ── черга-оренда (T16 крок 1): lease → ingest(task_id) → закриття ─────────────
    checks.append(("lease простому юзеру → 401",
                   client.post("/api/collect/lease", headers=ahdr, json={}).status_code == 401, None))
    # limit — динамічно від числа джерел (хардкод 20 зламався, щойно джерел стало 28)
    lr = client.post("/api/collect/lease",
                     json={"limit": len(qingest.HTML_SOURCES)}, headers=chdr).json()
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

    # «Тихий нуль» (2026-07-23): page-сторінка, з якої адаптер не видобув ЖОДНОЇ
    # позиції (челендж/staging-шелл/зламана розмітка) — це збій, не успіх. Раніше
    # закривалась ok і добу вдавала здорову (впіймано на першому render-зборі
    # MasterZoo). Мусить: fail-статус із причиною + бекоф (fail_count росте).
    with psycopg.connect(URL, autocommit=True) as c:
        zero_url = c.execute(
            "SELECT url FROM collect_task WHERE source='Moyo' AND leased_by IS NULL "
            "AND url <> %s ORDER BY task_id DESC LIMIT 1", (moyo_url,)).fetchone()[0]
        c.execute("UPDATE collect_task SET last_done_at = NULL, last_status = NULL, "
                  "fail_count = 0 WHERE source='Moyo' AND url = %s", (zero_url,))
    zr = client.post("/api/ingest/html", headers=chdr, json={
        "source": "Moyo", "url": zero_url, "html": "<html><body>жодної картки</body></html>"})
    checks.append(("тихий нуль: ingest 200, задача закрита (не висить)",
                   zr.status_code == 200 and zr.json().get("task_closed") is True
                   and zr.json().get("accepted") in (0, None), zr.json()))
    with psycopg.connect(URL, autocommit=True) as c:
        z = c.execute("SELECT last_status, fail_count, not_before > now() FROM collect_task "
                      "WHERE source='Moyo' AND url=%s", (zero_url,)).fetchone()
    checks.append(("тихий нуль → fail-статус із причиною + бекоф",
                   z is not None and str(z[0]).startswith("fail:0 позицій")
                   and z[1] == 1 and z[2] is True, z))

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

    # ── найпідступніший стан: телефон ЖИВИЙ і бере роботу, але кожен запит падає ──
    # Сталось 2026-07-21 о 16:20: колектор прокинувся, взяв по задачі на кожну з
    # восьми крамниць, усі вісім упали з «Connection failure» — а показник звітував
    # «Збір працює · останній 2 хв тому», бо міряв БУДЬ-ЯКУ активність. Свіжих цін не
    # з'явилось жодної. Показник, який світиться зеленим саме тоді, коли все зламано,
    # гірший за відсутній: на нього покладаються.
    # Беремо задачі, які ще не мали успіху, щоб не затерти «ok»-рядки з попередньої
    # перевірки — свіжість мусить лишитись порахованою від них (≈300 хв).
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE collect_task SET last_done_at = now(), "
                  "last_status = 'fail:Connection failure' "
                  "WHERE task_id IN (SELECT task_id FROM collect_task "
                  "                  WHERE last_status IS DISTINCT FROM 'ok' LIMIT 3)")
    h3 = client.get("/api/collect/health", headers=chdr).json()
    checks.append(("health: спроби є, успіхів нема → not ok + «запити падають»",
                   h3.get("ok") is False and "падають" in (h3.get("note") or "")
                   and h3.get("fails_1h", 0) >= 3, h3))
    checks.append(("health: свіжість — від УСПІШНОГО збору, а не від останньої спроби",
                   280 <= (h3.get("silent_min") or 0) <= 320, h3.get("silent_min")))
    checks.append(("health: спроба видима окремо від успіху (last_try_at)",
                   h3.get("last_try_at") is not None
                   and h3.get("last_try_at") != h3.get("last_done_at"), h3))

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

    # ── S15: адмін-панель (ролі / керування акаунтами / метрики) ─────────────────
    # ролі роздає власник напряму в БД (trusted-people) — робимо акаунти admin/moderator
    for _lim in (_rl.login_limiter, _rl.register_limiter):     # burst логінів нижче
        _lim._hits.clear()
    for em, pw in (("admin1@hapay.today", "adminpass1"), ("mod@hapay.today", "modpass12"),
                   ("victim@hapay.today", "victimpass"), ("victim2@hapay.today", "victim2pass")):
        client.post("/api/auth/register", json={"email": em, "password": pw})
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE app_user SET role='admin' WHERE lower(email)='admin1@hapay.today'")
        c.execute("UPDATE app_user SET role='moderator' WHERE lower(email)='mod@hapay.today'")
        uids = dict(c.execute(
            "SELECT lower(email), user_id FROM app_user WHERE lower(email) = ANY(%s)",
            (["admin1@hapay.today", "mod@hapay.today", "victim@hapay.today",
              "victim2@hapay.today", "collector@hapay.today"],)).fetchall())
    admtok = client.post("/api/auth/login",
                         json={"email": "admin1@hapay.today", "password": "adminpass1"}).json()
    checks.append(("login admin1 → role=admin", admtok.get("role") == "admin", admtok.get("role")))
    admhdr = {"Authorization": f"Bearer {admtok.get('token', '')}"}
    modtok = client.post("/api/auth/login",
                         json={"email": "mod@hapay.today", "password": "modpass12"}).json()
    modhdr = {"Authorization": f"Bearer {modtok.get('token', '')}"}

    # гейти списку/метрик: user → 403, moderator/admin → 200
    checks.append(("admin/users простому юзеру → 403",
                   client.get("/api/admin/users", headers=ahdr).status_code == 403, None))
    checks.append(("admin/users без токена → 401",
                   client.get("/api/admin/users").status_code == 401, None))
    au = client.get("/api/admin/users", headers=modhdr)
    checks.append(("admin/users модератору → 200 + сторінка акаунтів",
                   au.status_code == 200 and any(u["email"] == "victim@hapay.today"
                                                 for u in au.json()["users"]), au.status_code))
    checks.append(("admin/users несе пагінацію (total/page/pages)",
                   all(k in au.json() for k in ("total", "page", "pages", "per_page"))
                   and au.json()["total"] >= 4, {k: au.json().get(k) for k in ("total", "pages")}))
    checks.append(("картка акаунта несе last_login_at (був у БД, але не показувався)",
                   "last_login_at" in au.json()["users"][0], list(au.json()["users"][0])))

    # ── S16 П2: пошук / фільтри / пагінація ──────────────────────────────────────
    sq = client.get("/api/admin/users?q=victim", headers=modhdr).json()
    checks.append(("пошук q=victim → лише victim-акаунти",
                   sq["total"] == 2 and all("victim" in u["email"] for u in sq["users"]),
                   [u["email"] for u in sq["users"]]))
    checks.append(("пошук регістронезалежний (q=VICTIM)",
                   client.get("/api/admin/users?q=VICTIM", headers=modhdr).json()["total"] == 2,
                   None))
    checks.append(("пошук неіснуючого → 0, не помилка",
                   client.get("/api/admin/users?q=zzz-нема", headers=modhdr).json()["total"] == 0,
                   None))
    # ILIKE-спецсимвол у запиті не має валити пошук (значення йде ПАРАМЕТРОМ)
    checks.append(("пошук зі спецсимволом ILIKE (%) не ламає запит",
                   client.get("/api/admin/users?q=%25", headers=modhdr).status_code == 200, None))
    fr_ = client.get("/api/admin/users?role=admin", headers=modhdr).json()
    checks.append(("фільтр role=admin → лише адміни",
                   fr_["total"] >= 1 and all(u["role"] == "admin" for u in fr_["users"]),
                   [u["role"] for u in fr_["users"]]))
    checks.append(("фільтр невідомої ролі → 400",
                   client.get("/api/admin/users?role=superking",
                              headers=modhdr).status_code == 400, None))
    checks.append(("фільтр active=false → лише заблоковані (зараз жодного)",
                   all(not u["is_active"] for u in
                       client.get("/api/admin/users?active=false", headers=modhdr).json()["users"]),
                   None))
    pg1 = client.get("/api/admin/users?page=999", headers=modhdr).json()
    checks.append(("сторінка за межею → порожній список, total збережено",
                   pg1["users"] == [] and pg1["total"] >= 4, pg1["total"]))

    # ── S16 П1: метрики продукту (не лише акаунти) ───────────────────────────────
    am = client.get("/api/admin/metrics", headers=admhdr)
    mj = am.json()
    checks.append(("metrics: акаунти по ролях + реєстрації/активні",
                   am.status_code == 200
                   and mj["accounts"]["by_role"].get("admin", 0) >= 1
                   and mj["accounts"]["total"] >= 4
                   and all(k in mj["accounts"] for k in ("reg_7d", "reg_30d", "active_7d")),
                   mj.get("accounts")))
    checks.append(("metrics: дані (товари/снапшоти/події + приріст за добу)",
                   all(k in mj["data"] for k in ("products", "snapshots", "events",
                                                 "categories", "sources",
                                                 "products_1d", "snapshots_1d"))
                   and mj["data"]["products"] > 0 and mj["data"]["snapshots"] > 0,
                   mj.get("data")))
    badges = {b["state"]: b for b in mj["detection"]["badges"]}
    checks.append(("metrics: детекція несе ВСІ 5 бейджів, зокрема нульові",
                   len(mj["detection"]["badges"]) == 5
                   and "verified" in badges and "pumped" in badges
                   and all("total" in b and "d7" in b for b in mj["detection"]["badges"]),
                   [(b["state"], b["total"]) for b in mj["detection"]["badges"]]))
    # тихий нуль — визнаний дефект показників: нульовий бейдж мусить БУТИ у відповіді
    checks.append(("нульовий бейдж не зникає з відповіді (тихий нуль)",
                   badges["verified"]["total"] == 0, badges["verified"]))
    checks.append(("metrics: declared порахований (сід дав 8+)",
                   badges["declared"]["total"] >= 8, badges["declared"]))
    checks.append(("metrics: збір по крамницях (source/tasks/ok/fail)",
                   isinstance(mj["collect"]["stores"], list)
                   and all(k in mj["collect"]["stores"][0]
                           for k in ("source", "tasks", "ok", "fail", "ok_min")),
                   mj["collect"]["stores"][:2]))
    checks.append(("metrics: стан збору з collect_health (без другого визначення)",
                   "health" in mj["collect"] and "note" in mj["collect"]["health"],
                   mj["collect"].get("health", {}).get("note")))
    checks.append(("metrics простому юзеру → 403",
                   client.get("/api/admin/metrics", headers=ahdr).status_code == 403, None))

    # зміна ролі — ЛИШЕ admin (moderator не може)
    checks.append(("set_role модератором → 403 (лише admin)",
                   client.post(f"/api/admin/users/{uids['victim@hapay.today']}/role",
                               json={"role": "moderator"}, headers=modhdr).status_code == 403, None))
    sr = client.post(f"/api/admin/users/{uids['victim@hapay.today']}/role",
                     json={"role": "moderator"}, headers=admhdr)
    checks.append(("set_role адміном victim→moderator → 200",
                   sr.status_code == 200 and sr.json().get("role") == "moderator", sr.json()))
    checks.append(("зміна відображена у списку",
                   any(u["email"] == "victim@hapay.today" and u["role"] == "moderator"
                       for u in client.get("/api/admin/users",
                                           headers=admhdr).json()["users"]), None))
    # анти-self-lockout: адмін не змінює ВЛАСНУ роль
    checks.append(("set_role над собою → 400 (анти-self-lockout)",
                   client.post(f"/api/admin/users/{uids['admin1@hapay.today']}/role",
                               json={"role": "user"}, headers=admhdr).status_code == 400, None))
    checks.append(("set_role невідома роль → 400",
                   client.post(f"/api/admin/users/{uids['victim@hapay.today']}/role",
                               json={"role": "superking"}, headers=admhdr).status_code == 400, None))

    # бан: moderator не чіпає admin/moderator; user банить; забанений не входить
    checks.append(("moderator банить admin → 403",
                   client.post(f"/api/admin/users/{uids['admin1@hapay.today']}/ban",
                               json={"active": False}, headers=modhdr).status_code == 403, None))
    checks.append(("admin банить сам себе → 400",
                   client.post(f"/api/admin/users/{uids['admin1@hapay.today']}/ban",
                               json={"active": False}, headers=admhdr).status_code == 400, None))
    checks.append(("ban без active:bool → 400",
                   client.post(f"/api/admin/users/{uids['victim2@hapay.today']}/ban",
                               json={}, headers=admhdr).status_code == 400, None))
    bn = client.post(f"/api/admin/users/{uids['victim2@hapay.today']}/ban",
                     json={"active": False}, headers=modhdr)
    checks.append(("moderator банить простого user → 200", bn.status_code == 200, bn.json()))
    checks.append(("забанений user не входить → 403",
                   client.post("/api/auth/login",
                               json={"email": "victim2@hapay.today",
                                     "password": "victim2pass"}).status_code == 403, None))
    checks.append(("розбан адміном → 200 + вхід відновлено",
                   client.post(f"/api/admin/users/{uids['victim2@hapay.today']}/ban",
                               json={"active": True}, headers=admhdr).status_code == 200
                   and client.post("/api/auth/login",
                                   json={"email": "victim2@hapay.today",
                                         "password": "victim2pass"}).status_code == 200, None))
    # політика зама (рішення оператора 2026-07-26): moderator керує user + collector
    checks.append(("moderator банить collector → 200 (політика Users+collectors)",
                   client.post(f"/api/admin/users/{uids['collector@hapay.today']}/ban",
                               json={"active": False}, headers=modhdr).status_code == 200, None))
    client.post(f"/api/admin/users/{uids['collector@hapay.today']}/ban",   # розбан назад
                json={"active": True}, headers=admhdr)

    # last-admin guard (рівень db): демоут ЄДИНОГО активного admin забороняється, навіть
    # якщо викликано в обхід self-check (актор ≠ ціль). admin1 — єдиний admin.
    try:
        with psycopg.connect(URL, autocommit=True) as c:
            _qdb.set_user_role(c, uids["mod@hapay.today"], uids["admin1@hapay.today"], "user")
        checks.append(("демоут останнього admin → AdminError", False, "не кинуло"))
    except _qdb.AdminError:
        checks.append(("демоут останнього admin → AdminError", True, None))

    # аудит: кожна мутація лишила слід (set_role + ban/unban ≥ 3 записи)
    with psycopg.connect(URL) as c:
        naudit = c.execute("SELECT count(*) FROM admin_audit").fetchone()[0]
        acts = set(r[0] for r in c.execute("SELECT DISTINCT action FROM admin_audit").fetchall())
    checks.append(("admin_audit пише слід (set_role+set_active)",
                   naudit >= 3 and {"set_role", "set_active"} <= acts, (naudit, acts)))

    # ── S16: права беруться з БАЗИ, не з токена ──────────────────────────────────
    # Знайдено живцем 2026-07-26: роль зашита в JWT на момент видачі, тож підвищений
    # юзер не отримував прав до перелогіну, а ЗНИЖЕНИЙ адмін зберігав би повні права
    # до кінця життя токена — відібрати права було неможливо.
    up = signup("promoted@hapay.today", "promotedpass")
    uphdr = {"Authorization": f"Bearer {up.get('token', '')}"}     # токен видано з role=user
    checks.append(("свіжий юзер в адмін-панель → 403",
                   client.get("/api/admin/users", headers=uphdr).status_code == 403, None))
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE app_user SET role='moderator' WHERE lower(email)='promoted@hapay.today'")
    checks.append(("підвищення діє БЕЗ перелогіну (той самий токен) → 200",
                   client.get("/api/admin/users", headers=uphdr).status_code == 200, None))
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE app_user SET role='user' WHERE lower(email)='promoted@hapay.today'")
    checks.append(("зниження діє НЕГАЙНО (старий токен уже без прав) → 403",
                   client.get("/api/admin/users", headers=uphdr).status_code == 403, None))
    # бан мусить діяти на ЧИННУ сесію, не лише на новий вхід
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE app_user SET is_active=false WHERE lower(email)='promoted@hapay.today'")
    checks.append(("забанений із живим токеном втрачає доступ до /api/me → 403",
                   client.get("/api/me", headers=uphdr).status_code == 403, None))
    checks.append(("забанений із живим токеном не читає watchlist → 403",
                   client.get("/api/me/watchlist", headers=uphdr).status_code == 403, None))
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE app_user SET is_active=true WHERE lower(email)='promoted@hapay.today'")
    checks.append(("розбан повертає доступ тим самим токеном",
                   client.get("/api/me", headers=uphdr).status_code == 200, None))
    # той самий принцип для збору: знижений колектор більше не інджестить
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE app_user SET role='user' WHERE lower(email)='collector@hapay.today'")
    checks.append(("знижений колектор більше не інджестить → 401",
                   client.post("/api/ingest/html", headers=chdr,
                               json={"source": "Foxtrot",
                                     "url": "https://www.foxtrot.com.ua/uk/shop/x.html",
                                     "html": "<html></html>"}).status_code == 401, None))
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE app_user SET role='collector' WHERE lower(email)='collector@hapay.today'")

    # ── S16 П3: журнал аудиту (до S16 admin_audit була write-only) ───────────────
    aud = client.get("/api/admin/audit", headers=modhdr)
    aj = aud.json()
    checks.append(("admin/audit модератору → 200 + записи з пагінацією",
                   aud.status_code == 200 and aj["total"] >= 3
                   and all(k in aj for k in ("entries", "page", "pages")), aj.get("total")))
    checks.append(("запис журналу читабельний: хто/що/кому + email-знімок",
                   all(k in aj["entries"][0] for k in
                       ("actor_email", "action", "target_email", "detail", "created_at")),
                   aj["entries"][0]))
    checks.append(("журнал сортовано найновішим догори",
                   [e["audit_id"] for e in aj["entries"]]
                   == sorted((e["audit_id"] for e in aj["entries"]), reverse=True),
                   [e["audit_id"] for e in aj["entries"][:5]]))
    fa = client.get("/api/admin/audit?action=set_role", headers=modhdr).json()
    checks.append(("фільтр журналу за дією",
                   fa["total"] >= 1 and all(e["action"] == "set_role" for e in fa["entries"]),
                   [e["action"] for e in fa["entries"]]))
    checks.append(("журнал простому юзеру → 403",
                   client.get("/api/admin/audit", headers=ahdr).status_code == 403, None))

    # ── S16 П2: картка акаунта ───────────────────────────────────────────────────
    det = client.get(f"/api/admin/users/{uids['victim@hapay.today']}", headers=modhdr)
    dj = det.json()
    checks.append(("картка акаунта: профіль + стеження + адмін-дії над ним",
                   det.status_code == 200 and dj["email"] == "victim@hapay.today"
                   and isinstance(dj["watchlist"], list) and isinstance(dj["audit"], list),
                   {k: dj.get(k) for k in ("email", "role")}))
    checks.append(("картка показує адмін-дії саме над цим акаунтом (зміна ролі)",
                   any(e["action"] == "set_role" for e in dj["audit"]),
                   [e["action"] for e in dj["audit"]]))
    checks.append(("картка неіснуючого акаунта → 404",
                   client.get("/api/admin/users/999999", headers=modhdr).status_code == 404, None))
    checks.append(("картка простому юзеру → 403",
                   client.get(f"/api/admin/users/{uids['victim@hapay.today']}",
                              headers=ahdr).status_code == 403, None))

    # ── S16 П4: дії над акаунтом ─────────────────────────────────────────────────
    for _lim in (_rl.email_limiter,):
        _lim._hits.clear()
    vr2 = client.post(f"/api/admin/users/{uids['victim@hapay.today']}/verify", headers=modhdr)
    checks.append(("ручне підтвердження email → 200 + verified",
                   vr2.status_code == 200 and vr2.json().get("email_verified") is True, vr2.json()))
    checks.append(("ручний verify лишив слід в аудиті",
                   any(e["action"] == "verify_email" for e in
                       client.get("/api/admin/audit", headers=modhdr).json()["entries"]), None))
    checks.append(("ручний verify простому юзеру → 403",
                   client.post(f"/api/admin/users/{uids['victim@hapay.today']}/verify",
                               headers=ahdr).status_code == 403, None))
    sr2 = client.post(f"/api/admin/users/{uids['victim@hapay.today']}/send-reset", headers=modhdr)
    checks.append(("надсилання скидання пароля → 200 + слід в аудиті",
                   sr2.status_code == 200
                   and any(e["action"] == "send_reset" for e in
                           client.get("/api/admin/audit", headers=modhdr).json()["entries"]),
                   sr2.json()))
    checks.append(("send-reset неіснуючому → 404",
                   client.post("/api/admin/users/999999/send-reset",
                               headers=modhdr).status_code == 404, None))

    # видалення — ЛИШЕ admin, незворотне
    checks.append(("видалення акаунта модератором → 403",
                   client.delete(f"/api/admin/users/{uids['victim@hapay.today']}",
                                 headers=modhdr).status_code == 403, None))
    checks.append(("видалення СЕБЕ → 400",
                   client.delete(f"/api/admin/users/{uids['admin1@hapay.today']}",
                                 headers=admhdr).status_code == 400, None))
    # останній активний admin не видаляється навіть іншим адміном (db-рівень)
    try:
        with psycopg.connect(URL, autocommit=True) as c:
            _qdb.delete_user(c, uids["mod@hapay.today"], uids["admin1@hapay.today"])
        checks.append(("видалення останнього admin → AdminError", False, "не кинуло"))
    except _qdb.AdminError:
        checks.append(("видалення останнього admin → AdminError", True, None))

    dl = client.delete(f"/api/admin/users/{uids['victim@hapay.today']}", headers=admhdr)
    checks.append(("видалення адміном → 200", dl.status_code == 200, dl.json()))
    checks.append(("видалений акаунт зник зі списку",
                   client.get("/api/admin/users?q=victim@", headers=modhdr).json()["total"] == 0,
                   None))
    checks.append(("видалений не входить (акаунта нема) → 401",
                   client.post("/api/auth/login", json={"email": "victim@hapay.today",
                                                        "password": "victimpass"}).status_code == 401,
                   None))
    # ГОЛОВНЕ (0171): слід у журналі пережив видалення акаунта — email лишився знімком
    after = client.get("/api/admin/audit", headers=modhdr).json()
    kept = [e for e in after["entries"] if e.get("target_email") == "victim@hapay.today"]
    checks.append(("журнал пережив видалення: email-знімок лишився, target_id обнулено",
                   len(kept) >= 2 and all(e["target_id"] is None for e in kept),
                   [(e["action"], e["target_id"], e["target_email"]) for e in kept[:3]]))
    checks.append(("сам факт видалення записано в журнал",
                   any(e["action"] == "delete_user" for e in kept),
                   [e["action"] for e in kept]))

    # ── SEO: те, що бачить БОТ (S25) ─────────────────────────────────────────────
    # Сайт малюється клієнтом, тож усе нижче — єдине, що взагалі бачить бот прев'ю
    # посилання в Telegram і краулер. Тест живий, бо sitemap — це SQL: перший його
    # варіант посилався на неіснуючу колонку `de.detected_at` і впав 500 уже НА
    # ПРОДІ, бо жоден тест того запиту не виконував.
    import json as _json
    import re as _re

    spid = client.get("/api/discounts").json()[0]["store_product_id"]
    pg = client.get(f"/product/{spid}", headers={"accept": "text/html"})
    body = pg.text
    checks.append(("сторінка товару → 200 HTML", pg.status_code == 200
                   and "text/html" in pg.headers.get("content-type", ""), pg.status_code))
    for tag in ("og:title", "og:description", "og:url", "og:image", "twitter:card"):
        checks.append((f"прев'ю: {tag} у розмітці", tag in body, None))
    checks.append(("прев'ю: canonical на цей товар",
                   f'rel="canonical" href="https://hapay.today/product/{spid}"' in body, None))

    ld = _re.search(r'application/ld\+json">(.*?)</script>', body, _re.S)
    checks.append(("JSON-LD присутній і валідний", bool(ld), None))
    if ld:
        data = _json.loads(ld.group(1))
        checks.append(("JSON-LD: Product з ціною й валютою",
                       data.get("@type") == "Product"
                       and data["offers"]["priceCurrency"] == "UAH"
                       and "price" in data["offers"], data.get("offers")))
        # інваріант B: опису крамниці ми не зберігаємо, тож і публікувати нема чого
        checks.append(("JSON-LD БЕЗ description (інваріант B)",
                       "description" not in data, list(data)))
        checks.append(("JSON-LD БЕЗ image (фото — не наше)",
                       "image" not in data, list(data)))

    checks.append(("назва товару є в HTML до будь-якого JS",
                   "<h1>" in body, None))

    nf = client.get("/product/999999999", headers={"accept": "text/html"})
    checks.append(("неіснуючий товар → сторінка, не виняток",
                   nf.status_code == 200 and "noindex" in nf.text, nf.status_code))

    rb = client.get("/robots.txt")
    checks.append(("robots.txt віддається", rb.status_code == 200
                   and "Sitemap:" in rb.text, rb.status_code))
    checks.append(("robots НЕ закриває /s/ (там css/js і картинка прев'ю)",
                   "Disallow: /s/" not in rb.text, rb.text))

    sm = client.get("/sitemap.xml")
    checks.append(("sitemap.xml → 200 XML", sm.status_code == 200
                   and "xml" in sm.headers.get("content-type", ""), sm.status_code))
    checks.append(("sitemap містить головну, каталог і сторінки товарів",
                   "<loc>https://hapay.today/</loc>" in sm.text
                   and "/catalog" in sm.text and f"/product/{spid}" in sm.text,
                   sm.text[:200]))

    h404 = client.get("/take-storinky-nemaye", headers={"accept": "text/html"})
    checks.append(("404 для людини → HTML-сторінка, не JSON",
                   h404.status_code == 404 and "<html" in h404.text, h404.status_code))
    j404 = client.get("/api/nemaye-takogo", headers={"accept": "application/json"})
    checks.append(("404 для API лишився JSON",
                   j404.status_code == 404 and "detail" in j404.json(), j404.status_code))

    cmp_pg = client.get("/compare", headers={"accept": "text/html"})
    checks.append(("/compare → сторінка", cmp_pg.status_code == 200
                   and "cmp-t" in cmp_pg.text, cmp_pg.status_code))
    # мітка версії: без неї стара копія css/js зустрічається з новою розміткою
    checks.append(("css/js віддаються з міткою версії",
                   "/s/app.css?v=" in cmp_pg.text and "/s/app.js?v=" in cmp_pg.text,
                   None))

    # ── сторінки-обличчя (S27) ───────────────────────────────────────────────────
    # Категорійні адреси мусять мати ВЛАСНИЙ титул і canonical на себе. До 27.07 усі
    # 148 віддавали один заголовок і canonical на /catalog — тобто sitemap перелічував
    # сторінки, які самі казали краулеру «я копія».
    cat_slug = client.get("/api/categories").json()[0]["slug"]
    base = client.get("/catalog", headers={"accept": "text/html"}).text
    withc = client.get(f"/catalog?c={cat_slug}", headers={"accept": "text/html"}).text
    t_of = lambda h: (_re.search(r"<title>(.*?)</title>", h) or ["", ""])[1]
    checks.append(("категорія має ВЛАСНИЙ <title>", t_of(base) != t_of(withc),
                   (t_of(base), t_of(withc))))
    checks.append(("категорія: canonical на СЕБЕ, не на /catalog",
                   f'rel="canonical" href="https://hapay.today/catalog?c={cat_slug}"' in withc,
                   None))

    pumped = client.get("/catalog?b=pumped", headers={"accept": "text/html"}).text
    checks.append(("?b=pumped має власне обличчя",
                   "завищеною" in t_of(pumped).lower() or "завищен" in pumped[:3000],
                   t_of(pumped)))
    srch = client.get("/catalog?q=acer", headers={"accept": "text/html"}).text
    checks.append(("сторінка пошуку — noindex (не смітимо власною видачею)",
                   "noindex" in srch, t_of(srch)))

    for path, needle in (("/how", "перевіряємо"), ("/delete-account", "Видалення"),
                         ("/stores", "рамниц")):
        r = client.get(path, headers={"accept": "text/html"})
        checks.append((f"{path} → сторінка", r.status_code == 200 and needle in r.text,
                       r.status_code))

    stores = client.get("/api/stores")
    checks.append(("/api/stores → список із фактами", stores.status_code == 200
                   and isinstance(stores.json(), list), stores.status_code))
    slist = stores.json() if stores.status_code == 200 else []
    if slist:
        sslug = slist[0]["slug"]
        checks.append(("крамниця має slug у нижньому регістрі", sslug == sslug.lower(), sslug))
        sp = client.get(f"/store/{sslug}", headers={"accept": "text/html"})
        checks.append((f"/store/{sslug} → сторінка з власним title",
                       sp.status_code == 200 and slist[0]["name"] in t_of(sp.text), sp.status_code))
        one = client.get(f"/api/store/{sslug}").json()
        checks.append(("факти крамниці: усі лічильники присутні",
                       all(k in one for k in ("products", "discounts", "verified", "pumped")),
                       list(one)))
    miss = client.get("/store/takoyi-nemaye", headers={"accept": "text/html"})
    checks.append(("невідома крамниця → 404 і noindex",
                   miss.status_code == 404 and "noindex" in miss.text, miss.status_code))

    # ── самостійне видалення акаунта (вимога Google Play) ────────────────────────
    # signup() повертає ВІДПОВІДЬ ЛОГІНУ (dict), не голий токен — сюди я підставив
    # рядок із голови, і CI спіймав це TypeError-ом за 30 рядків від причини.
    dele = signup("bye@hapay.today", "byepassword")["token"]
    delh = {"Authorization": "Bearer " + dele}
    checks.append(("своє видалення без токена → 401",
                   client.delete("/api/me").status_code == 401, None))
    dd = client.delete("/api/me", headers=delh)
    checks.append(("DELETE /api/me → 200", dd.status_code == 200, dd.text[:120]))
    checks.append(("після видалення токен більше не працює",
                   client.get("/api/me", headers=delh).status_code == 401, None))
    checks.append(("видалений не може увійти",
                   client.post("/api/auth/login", json={"email": "bye@hapay.today",
                                                        "password": "byepassword"}).status_code == 401,
                   None))
    # захист: останній активний адмін не може піти й лишити систему без керування
    with psycopg.connect(URL, autocommit=True) as c:
        try:
            _qdb.delete_own_account(c, uids["admin1@hapay.today"])
            checks.append(("останній адмін видаляє себе → AdminError", False, "не кинуло"))
        except _qdb.AdminError:
            checks.append(("останній адмін видаляє себе → AdminError", True, None))

    # ── виміряні зниження цін (S28) ──────────────────────────────────────────────
    dr = client.get("/api/drops?days=1")
    checks.append(("/api/drops → 200 зі зведенням і списком",
                   dr.status_code == 200 and "summary" in dr.json() and "items" in dr.json(),
                   dr.status_code))
    dsum = dr.json().get("summary") or {}
    checks.append(("зведення має down/up/compared — подорожчання показуємо навмисно",
                   all(k in dsum for k in ("down", "up", "compared")), list(dsum)))
    checks.append(("порядок за замовчуванням — fresh (за відсотком артефакти йдуть першими)",
                   dr.json().get("order") == "fresh", dr.json().get("order")))
    checks.append(("order=deep приймається",
                   client.get("/api/drops?days=1&order=deep").status_code == 200, None))
    checks.append(("невідомий order → 400, а не тихий фолбек",
                   client.get("/api/drops?order=abyrvalg").status_code == 400, None))
    checks.append(("days поза межами → 422",
                   client.get("/api/drops?days=99").status_code == 422, None))
    dpg = client.get("/drops", headers={"accept": "text/html"})
    checks.append(("/drops → сторінка", dpg.status_code == 200
                   and "подешевшало" in dpg.text.lower(), dpg.status_code))
    # застереження про фасування мусить бути на сторінці, а не лише в коментарі
    checks.append(("сторінка попереджає про зміну варіанта товару",
                   "пакування" in dpg.text, None))

    # ── цільова ціна, стеження за запитом, листи (S29) ───────────────────────────
    wu = signup("watcher@hapay.today", "watcherpass")["token"]
    wh = {"Authorization": "Bearer " + wu}
    spid_w = client.get("/api/discounts").json()[0]["store_product_id"]

    bad_t = client.post("/api/me/watchlist", headers=wh,
                        json={"kind": "store_product", "ref_id": spid_w, "target_kop": 0})
    checks.append(("ціль 0 → 400 (це помилка вводу, не намір)", bad_t.status_code == 400, None))

    noq = client.post("/api/me/watchlist", headers=wh,
                      json={"kind": "query", "query_text": "навушники"})
    checks.append(("стеження за запитом БЕЗ цілі → 400 (це була б розсилка)",
                   noq.status_code == 400, noq.text[:80]))
    okq = client.post("/api/me/watchlist", headers=wh,
                      json={"kind": "query", "query_text": "навушники", "target_kop": 100000})
    checks.append(("стеження за запитом із ціллю → 200", okq.status_code == 200, okq.text[:80]))
    checks.append(("повторний той самий запит не дублюється",
                   client.post("/api/me/watchlist", headers=wh,
                               json={"kind": "query", "query_text": "навушники",
                                     "target_kop": 100000}).json()["watchlist_id"]
                   == okq.json()["watchlist_id"], None))

    w1 = client.post("/api/me/watchlist", headers=wh,
                     json={"kind": "store_product", "ref_id": spid_w,
                           "target_kop": 1}).json()
    checks.append(("ціль повертається у відповіді", w1.get("target_kop") == 1, w1))
    checks.append(("ціль видно у списку стеження",
                   any(x.get("target_kop") == 1 for x in
                       client.get("/api/me/watchlist", headers=wh).json()), None))

    # ГОЛОВНЕ: з ціллю 1 копійка жодне реальне зниження не має «спрацювати»
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("UPDATE watchlist SET price_at_add_kop = 999999999 WHERE watchlist_id = %s",
                  (w1["watchlist_id"],))
    checks.append(("зниження НЕ повідомляється, поки не досягнуто цілі",
                   not any(d["watchlist_id"] == w1["watchlist_id"]
                           for d in client.get("/api/me/watchlist/drops", headers=wh).json()),
                   None))
    pt = client.patch(f"/api/me/watchlist/{w1['watchlist_id']}", headers=wh,
                      json={"target_kop": 999999999})
    checks.append(("PATCH міняє ціль", pt.status_code == 200
                   and pt.json()["target_kop"] == 999999999, pt.text[:80]))
    checks.append(("після підняття цілі зниження зʼявляється",
                   any(d["watchlist_id"] == w1["watchlist_id"]
                       for d in client.get("/api/me/watchlist/drops", headers=wh).json()),
                   None))
    checks.append(("чужий запис не патчиться → 404",
                   client.patch("/api/me/watchlist/999999", headers=wh,
                                json={"target_kop": 100}).status_code == 404, None))

    # ack мусить ставити і ЧАС — без нього запобіжник частоти листів сліпий
    ids = [d["watchlist_id"] for d in client.get("/api/me/watchlist/drops", headers=wh).json()]
    client.post("/api/me/watchlist/drops/ack", headers=wh, json={"watchlist_ids": ids})
    with psycopg.connect(URL, autocommit=True) as c:
        stamped = c.execute("SELECT last_notified_at IS NOT NULL FROM watchlist "
                            " WHERE watchlist_id = %s", (w1["watchlist_id"],)).fetchone()[0]
    checks.append(("ack ставить last_notified_at (частота листів на нього спирається)",
                   stamped, None))

    # згода на листи
    checks.append(("/api/me віддає email_alerts (інакше вимикач бреше про стан)",
                   "email_alerts" in client.get("/api/me", headers=wh).json(), None))
    off = client.post("/api/me/alerts", headers=wh, json={"enabled": False})
    checks.append(("вимкнення листів → 200", off.status_code == 200
                   and off.json()["email_alerts"] is False, off.text[:60]))
    checks.append(("вимкнені листи → акаунт не потрапляє в розсилку",
                   not any(u["email"] == "watcher@hapay.today"
                           for u in _qdb.users_for_alerts(
                               psycopg.connect(URL, autocommit=True))), None))
    checks.append(("enabled не-булеве → 400",
                   client.post("/api/me/alerts", headers=wh,
                               json={"enabled": "так"}).status_code == 400, None))

    # відписка одним кліком: підпис прив'язаний до конкретного акаунта
    from api import auth as _qauth
    uid_w = client.get("/api/me", headers=wh).json()["user_id"]
    sig = _qauth.unsub_link(uid_w).split("s=")[1]
    checks.append(("підпис відписки не підходить до чужого id",
                   not _qauth.verify_unsub(uid_w + 1, sig), None))
    checks.append(("/unsubscribe без підпису → сторінка «недійсне», не виняток",
                   client.get("/unsubscribe", headers={"accept": "text/html"}).status_code == 200,
                   None))

    low = client.get(f"/api/product/{spid_w}/low")
    checks.append(("/low → мінімум РАЗОМ із вікном спостережень",
                   low.status_code == 200
                   and all(k in low.json() for k in ("low_kop", "days", "measurements",
                                                     "first_day")),
                   low.status_code))
    checks.append(("/low для неіснуючого товару → 404",
                   client.get("/api/product/999999999/low").status_code == 404, None))

    al = client.get("/.well-known/assetlinks.json")
    checks.append(("assetlinks без ANDROID_CERT_SHA256 → 404, а не порожній файл",
                   al.status_code == 404, al.status_code))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
