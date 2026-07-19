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
from api import auth as qauth
from api.initdata import verify_init_data, check_auth_age, InitDataError
from detection.runner import detect_pass

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Радар знижок — read-API")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEB_INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html")


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


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/categories")
def categories(conn=Depends(get_conn)):
    return qdb.categories(conn)


@app.get("/api/discounts")
def discounts(category: str | None = None, badge: str | None = None, q: str | None = None,
              sort: str = "verified", page: int = Query(0, ge=0), conn=Depends(get_conn)):
    return qdb.list_discounts(conn, category, badge, sort, limit=50, offset=page * 50, q=q)


@app.get("/api/product/{store_product_id}/history")
def history(store_product_id: int, conn=Depends(get_conn)):
    return qdb.product_history(conn, store_product_id)


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
    return qdb.add_watchlist_user(conn, int(claims["sub"]), kind,
                                  body.get("ref_id"), body.get("query_text"))


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


@app.post("/api/ingest/html")
def ingest_html(body: dict, collector=Depends(require_collector), conn=Depends(get_conn)):
    """Застосунок шле СИРИЙ HTML (зі свого резидентного IP) → СЕРВЕР парсить адаптером
    (§7.4 — не botnet; застосунок = «тупий фетчер»). Двофазно для hub: у відповіді —
    `discovered`-лендинги, які застосунок дотягне наступними викликами."""
    source, url, html = body.get("source"), body.get("url"), body.get("html")
    if not (isinstance(source, str) and isinstance(url, str) and isinstance(html, str)):
        raise HTTPException(400, "потрібні source, url, html (усі str)")
    try:
        result = qingest.ingest_html(conn, source, url, html)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if result.get("kind") == "page" and result.get("accepted"):
        result["events"] = detect_pass(conn)    # бейджі лише коли справді щось прийняли (§8.4)
    result["collector"] = collector
    return result
