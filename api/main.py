"""read-API + сервер Mini App (§8.10.1). FastAPI; клієнт без прямого доступу до БД.

BOT_TOKEN / DATABASE_URL — лише з env (Actions secret). Запуск локально:
  uvicorn api.main:app --reload
"""
from __future__ import annotations
import os
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

import re

from db.pool import get_pool
from api import db as qdb
from api import ingest as qingest
from api import qtasks
from api import auth as qauth
from api.initdata import verify_init_data, check_auth_age, InitDataError
from detection.runner import detect_pass

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Радар знижок — read-API")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
WEB_INDEX = os.path.join(WEB_DIR, "index.html")
_LEGAL = {"privacy", "terms", "support"}   # юр-сторінки (обов'язкові для сторів)


def get_conn():
    with get_pool().connection() as conn:
        yield conn


def require_user(x_init_data: str | None = Header(default=None)):
    """Гейт для write-ендпоінтів: перевіряємо підпис Telegram initData (§8.10.1)."""
    if not x_init_data:
        raise HTTPException(401, "немає X-Init-Data")
    try:
        payload = verify_init_data(x_init_data, BOT_TOKEN)
        check_auth_age(payload, int(time.time()))
    except InitDataError as e:
        raise HTTPException(401, f"initData: {e}")
    user = payload.get("user") or {}
    if "id" not in user:
        raise HTTPException(401, "немає user.id")
    return user


@app.get("/")
def index():
    return FileResponse(WEB_INDEX)


@app.get("/{page}")
def legal(page: str):
    """Юр-сторінки /privacy, /terms, /support (для App Store / Google Play)."""
    if page not in _LEGAL:
        raise HTTPException(404, "не знайдено")
    return FileResponse(os.path.join(WEB_DIR, f"{page}.html"), media_type="text/html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/categories")
def categories(conn=Depends(get_conn)):
    return qdb.categories(conn)


@app.get("/api/discounts")
def discounts(category: str | None = None, badge: str | None = None, q: str | None = None,
              sort: str = "verified", page: int = Query(0, ge=0),
              price_min: int | None = Query(None, ge=0),   # копійки (інв. A); фільтр за поточною ціною
              price_max: int | None = Query(None, ge=0),
              conn=Depends(get_conn)):
    return qdb.list_discounts(conn, category, badge, sort, limit=50, offset=page * 50, q=q,
                              price_min=price_min, price_max=price_max)


@app.get("/api/products")
def products(category: str | None = None, q: str | None = None, sort: str = "discount",
             page: int = Query(0, ge=0),
             price_min: int | None = Query(None, ge=0),
             price_max: int | None = Query(None, ge=0),
             only_discounts: bool = False, conn=Depends(get_conn)):
    """УСІ товари (не лише знижки) — повний прайс-агрегатор. `only_discounts=1` → лише знижкові."""
    return qdb.list_products(conn, category, sort, limit=50, offset=page * 50, q=q,
                             price_min=price_min, price_max=price_max, only_discounts=only_discounts)


@app.get("/api/product/{store_product_id}/history")
def history(store_product_id: int, conn=Depends(get_conn)):
    return qdb.product_history(conn, store_product_id)


@app.get("/api/product/{store_product_id}/offers")
def offers(store_product_id: int, conn=Depends(get_conn)):
    """«Де купити» (T15): той самий товар (mpn) у всіх крамницях, від найдешевшої."""
    return qdb.product_offers(conn, store_product_id)


@app.get("/api/watchlist")
def watchlist(user=Depends(require_user), conn=Depends(get_conn)):
    return qdb.list_watchlist(conn, int(user["id"]))


@app.post("/api/watchlist")
def add_watchlist(body: dict, user=Depends(require_user), conn=Depends(get_conn)):
    kind = body.get("kind")
    if kind not in ("category", "store_product", "query"):
        raise HTTPException(400, "kind ∈ category|store_product|query")
    return qdb.add_watchlist(conn, int(user["id"]), kind,
                             body.get("ref_id"), body.get("query_text"))


_COLLECTOR_ROLES = {"collector", "moderator", "admin"}


def require_collector(authorization: str | None = Header(default=None)):
    """Гейт ingest: статичний bearer-токен колектора (S10 — скрипти/GH Actions) АБО
    app-акаунт із роллю collector+ (S11 етап 3 — збір із застосунку). Повертає мітку
    колектора для провенансу (label токена або `acct:<user_id>`)."""
    label = qingest.collector_label(authorization)
    if label:
        return label
    claims = qauth.bearer_claims(authorization)
    if claims and claims.get("role") in _COLLECTOR_ROLES:
        return f"acct:{claims.get('sub')}"
    raise HTTPException(401, "потрібен токен колектора або акаунт із роллю collector")


# ── акаунти (S11): реєстрація / логін / профіль / watchlist на юзера ──────────────
def require_account(authorization: str | None = Header(default=None)):
    """Гейт для app-акаунтів: валідний JWT (api/auth). Повертає claims (sub, role)."""
    claims = qauth.bearer_claims(authorization)
    if claims is None:
        raise HTTPException(401, "потрібен валідний токен акаунта")
    return claims


@app.post("/api/auth/register")
def register(body: dict, conn=Depends(get_conn)):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "невірний email")
    if len(password) < qauth.MIN_PASSWORD:
        raise HTTPException(400, f"пароль ≥ {qauth.MIN_PASSWORD} символів")
    row = qdb.create_user(conn, email, qauth.hash_password(password))
    if row is None:
        raise HTTPException(409, "email уже зареєстрований")
    user_id, role = row
    try:
        return {"token": qauth.make_token(user_id, role), "role": role, "email": email}
    except qauth.AuthError as e:
        raise HTTPException(500, str(e))   # JWT_SECRET не заданий на сервері


@app.post("/api/auth/login")
def login(body: dict, conn=Depends(get_conn)):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    u = qdb.get_user_by_email(conn, email)
    # constant-ish: перевіряємо пароль навіть якщо юзера нема (проти user-enumeration за таймінгом)
    ok = u is not None and qauth.verify_password(password, u["password_hash"])
    if not ok:
        raise HTTPException(401, "невірний email або пароль")
    qdb.touch_login(conn, u["user_id"])
    try:
        return {"token": qauth.make_token(u["user_id"], u["role"]),
                "role": u["role"], "email": u["email"]}
    except qauth.AuthError as e:
        raise HTTPException(500, str(e))


@app.get("/api/me")
def me(claims=Depends(require_account), conn=Depends(get_conn)):
    u = qdb.get_user(conn, int(claims["sub"]))
    if u is None:
        raise HTTPException(401, "акаунт не існує")
    return u


@app.get("/api/me/watchlist")
def my_watchlist(claims=Depends(require_account), conn=Depends(get_conn)):
    return qdb.list_watchlist_user(conn, int(claims["sub"]))


@app.post("/api/me/watchlist")
def my_watchlist_add(body: dict, claims=Depends(require_account), conn=Depends(get_conn)):
    kind = body.get("kind")
    if kind not in ("category", "store_product", "query"):
        raise HTTPException(400, "kind ∈ category|store_product|query")
    ref_id = body.get("ref_id")
    if kind == "store_product" and not isinstance(ref_id, int):
        raise HTTPException(400, "ref_id обовʼязковий для store_product")
    return qdb.add_watchlist_user(conn, int(claims["sub"]), kind,
                                  ref_id, body.get("query_text"))


@app.get("/api/me/watchlist/drops")
def my_price_drops(claims=Depends(require_account), conn=Depends(get_conn)):
    """Відстежувані товари, що подешевшали від часу останнього сповіщення.
    Застосунок опитує це у фоні й показує ЛОКАЛЬНЕ сповіщення (без сторонніх
    push-сервісів — §7.7: жодної телеметрії назовні)."""
    return qdb.list_price_drops(conn, int(claims["sub"]))


@app.post("/api/me/watchlist/drops/ack")
def my_price_drops_ack(body: dict, claims=Depends(require_account), conn=Depends(get_conn)):
    """Підтвердити, що про зниження повідомлено — щоб не дзвонити вдруге про те саме."""
    ids = (body or {}).get("watchlist_ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise HTTPException(400, "watchlist_ids: список int")
    return {"acked": qdb.ack_price_drops(conn, int(claims["sub"]), ids)}


@app.delete("/api/me/watchlist/{watchlist_id}")
def my_watchlist_remove(watchlist_id: int, claims=Depends(require_account),
                        conn=Depends(get_conn)):
    """Прибрати зі стеження. Чужий рядок не видалиться (user_id у WHERE) → 404."""
    if not qdb.remove_watchlist_user(conn, int(claims["sub"]), watchlist_id):
        raise HTTPException(404, "нема такого запису")
    return {"ok": True}


@app.post("/api/ingest")
def ingest(body: dict, collector=Depends(require_collector), conn=Depends(get_conn)):
    """Довірений колектор шле зібране зі своєї резидентної мережі (§7.4 — не botnet).
    Сервер валідує КОЖЕН елемент (api/ingest), тоді детекція оновлює бейджі."""
    source = body.get("source")
    items = body.get("items")
    if not isinstance(source, str) or not isinstance(items, list):
        raise HTTPException(400, "потрібні source (str) та items (list)")
    try:
        result = qingest.ingest_batch(conn, source, items)
    except ValueError as e:
        raise HTTPException(400, str(e))
    result["events"] = detect_pass(conn)        # бейджі для щойно прийнятих (§8.4)
    result["collector"] = collector
    return result


@app.get("/api/collect/plan")
def collect_plan(collector=Depends(require_collector)):
    """Застосунок-колектор питає, ЩО тягнути. Сервер — авторитет над списком (додати
    крамницю = зміна лише тут, без оновлення застосунку в сторах)."""
    return {"targets": qingest.collect_plan(), "collector": collector}


# ── черга-оренда (T16): телефони ЗАБИРАЮТЬ роботу, сервер розганяє по часу ────────
@app.post("/api/collect/lease")
def collect_lease(body: dict | None = None, collector=Depends(require_collector),
                  conn=Depends(get_conn)):
    """Видати ≤limit дозрілих задач (по 1 на крамницю — розліт 15 хв/крамниця).
    Порожньо = все зібрано нещодавно; телефон засинає до наступного опитування."""
    qtasks.seed_tasks(conn)                 # ледачий сів: нове в HTML_SOURCES → у черзі
    body = body or {}
    limit = body.get("limit", 3)
    if not isinstance(limit, int):
        raise HTTPException(400, "limit має бути int")
    # `modes` (опц.) — робітник бере лише задачі свого режиму: PC-колектор ['fetch'],
    # телефон не шле й бере все. Валідуємо тип; невідомі режими просто нічого не дадуть.
    modes = body.get("modes")
    if modes is not None and not (isinstance(modes, list) and all(isinstance(m, str) for m in modes)):
        raise HTTPException(400, "modes має бути списком рядків")
    return {"tasks": qtasks.lease_tasks(conn, collector, limit, modes), "collector": collector}


@app.post("/api/collect/fail")
def collect_fail(body: dict, collector=Depends(require_collector), conn=Depends(get_conn)):
    """Телефон не зміг стягнути (403/капча/таймаут) → бекоф, не довбаємо крамницю."""
    task_id = body.get("task_id")
    if not isinstance(task_id, int):
        raise HTTPException(400, "потрібен task_id (int)")
    closed = qtasks.complete_task(conn, task_id, collector, ok=False,
                                  note=str(body.get("note") or "fetch")[:200])
    if not closed:
        raise HTTPException(409, "задача не твоя або оренда протухла")
    return {"ok": True}


@app.get("/api/collect/queue")
def collect_queue(collector=Depends(require_collector), conn=Depends(get_conn)):
    """Зріз черги (для оператора/діагностики): задачі/дозрілі/збійні по крамницях."""
    return {"sources": qtasks.queue_stats(conn), "collector": collector}


@app.get("/api/collect/health")
def collect_health(collector=Depends(require_collector), conn=Depends(get_conn)):
    """Чи живий збір — щоб тиха зупинка колектора не лишалась непоміченою годинами.
    Гейт колектора: показує внутрішній стан черги, не для сторонніх очей."""
    return qtasks.collect_health(conn)


@app.post("/api/ingest/html")
def ingest_html(body: dict, collector=Depends(require_collector), conn=Depends(get_conn)):
    """Застосунок шле СИРИЙ HTML (зі свого резидентного IP) → СЕРВЕР парсить адаптером
    (§7.4 — не botnet; застосунок = «тупий фетчер»). Двофазно для hub: у відповіді —
    `discovered`-лендинги; вони ж лягають у ЧЕРГУ (T16) для фонових колекторів.
    Опційний task_id — задача з черги закривається сама при успішному інджесті."""
    source, url, html = body.get("source"), body.get("url"), body.get("html")
    if not (isinstance(source, str) and isinstance(url, str) and isinstance(html, str)):
        raise HTTPException(400, "потрібні source, url, html (усі str)")
    try:
        result = qingest.ingest_html(conn, source, url, html)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if result.get("kind") == "hub" and result.get("discovered"):
        # лендинги — в чергу: фонові колектори розберуть їх із 15-хв розльотом,
        # а кнопковий режим може дотягнути одразу (обидва шляхи співіснують)
        result["enqueued"] = qtasks.enqueue_pages(conn, source, result["discovered"])
    if result.get("kind") == "page" and result.get("accepted"):
        result["events"] = detect_pass(conn)    # бейджі лише коли справді щось прийняли (§8.4)
    task_id = body.get("task_id")
    if isinstance(task_id, int):
        result["task_closed"] = qtasks.complete_task(conn, task_id, collector, ok=True)
    else:
        # Без task_id — це ручний прохід «зібрати все» (ходить за планом, не за чергою).
        # Сторінку таки зібрано, тож закриваємо задачу за (source, url): інакше черга
        # перезбирала б її вдруге, а last_done_at показував би «ще не брали».
        result["task_closed"] = qtasks.complete_by_url(conn, source, url)
    result["collector"] = collector
    return result
