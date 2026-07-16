"""read-API + сервер Mini App (§8.10.1). FastAPI; клієнт без прямого доступу до БД.

BOT_TOKEN / DATABASE_URL — лише з env (Actions secret). Запуск локально:
  uvicorn api.main:app --reload
"""
from __future__ import annotations
import os
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

from db.pool import get_pool
from api import db as qdb
from api.initdata import verify_init_data, check_auth_age, InitDataError

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
