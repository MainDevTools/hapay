"""read-API + сервер Mini App (§8.10.1). FastAPI; клієнт без прямого доступу до БД.

BOT_TOKEN / DATABASE_URL — лише з env (Actions secret). Запуск локально:
  uvicorn api.main:app --reload
"""
from __future__ import annotations
import os
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

import re

from db.pool import get_pool
from api import db as qdb
from api import ingest as qingest
from api import qtasks
from api import auth as qauth
from api import ratelimit as qrl
from api import email as qemail
from api.initdata import verify_init_data, check_auth_age, InitDataError
from detection.runner import detect_pass
from taxonomy import SECTION_ORDER

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


@app.get("/admin")
def admin_page():
    """Веб-панель (S16). Реєструється ДО catch-all `/{page}` — інакше той перехопив би
    шлях і віддав 404. Сторінка статична й без секретів: усі дані тягне через ті самі
    гейтовані /api/admin/*, токен бере з логіну й тримає в sessionStorage."""
    return FileResponse(os.path.join(WEB_DIR, "admin.html"), media_type="text/html")


# Сторінки сайту (S19). Кожна — окремий файл у web/; спільні стилі й скрипти лежать
# поруч і віддаються через /s/<файл>. УСІ ці маршрути мусять стояти ДО catch-all
# `/{page}` — інакше він перехопить шлях і віддасть 404 (на це вже наступали з /admin).
_PAGES = {"catalog", "login", "me"}
_ASSETS = {"app.css", "app.js", "catalog.js"}   # білий список: жодного обходу шляхом


@app.get("/s/{name}")
def asset(name: str):
    """Спільні стилі/скрипти. Список статичний — «..» чи будь-що інше просто не збігається."""
    if name not in _ASSETS:
        raise HTTPException(404, "не знайдено")
    kind = "text/css" if name.endswith(".css") else "application/javascript"
    return FileResponse(os.path.join(WEB_DIR, name), media_type=f"{kind}; charset=utf-8")


@app.get("/product/{store_product_id}")
def product_page(store_product_id: int):
    """Сторінка товару окремим URL — щоб на неї можна було послатись і поділитись
    (у шторці каталогу такої адреси не існує). Дані тягне той самий JS."""
    return FileResponse(os.path.join(WEB_DIR, "product.html"), media_type="text/html")


@app.get("/{page}")
def legal(page: str):
    """Сторінки сайту (S19) + юр-сторінки /privacy, /terms, /support (вимога сторів)."""
    if page in _PAGES:
        return FileResponse(os.path.join(WEB_DIR, f"{page}.html"), media_type="text/html")
    if page not in _LEGAL:
        raise HTTPException(404, "не знайдено")
    return FileResponse(os.path.join(WEB_DIR, f"{page}.html"), media_type="text/html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/categories")
def categories(conn=Depends(get_conn)):
    return qdb.categories(conn)


def _check_section(section: str | None):
    """Невідомий розділ — 400, а не порожня видача: порожньо виглядало б як «товарів
    нема», хоча насправді помилка в назві розділу."""
    if section is not None and section not in SECTION_ORDER:
        raise HTTPException(400, "невідомий розділ")


def _check_badge(badge: str | None):
    """Невідомий стан — 400, а не тиша. До 2026-07-26 `?badge=pumped` мовчки
    ігнорувався: клієнт бачив повний каталог, вважаючи, що фільтр застосовано."""
    if badge is not None and badge not in qdb.BADGE_FILTERS:
        raise HTTPException(400, f"badge ∈ {', '.join(qdb.BADGE_FILTERS)}")


@app.get("/api/discounts")
def discounts(category: str | None = None, section: str | None = None,
              badge: str | None = None, q: str | None = None,
              sort: str = "verified", page: int = Query(0, ge=0),
              price_min: int | None = Query(None, ge=0),   # копійки (інв. A); фільтр за поточною ціною
              price_max: int | None = Query(None, ge=0),
              conn=Depends(get_conn)):
    _check_badge(badge); _check_section(section)
    return qdb.list_discounts(conn, category, badge, sort, limit=50, offset=page * 50, q=q,
                              price_min=price_min, price_max=price_max, section=section)


@app.get("/api/products")
def products(category: str | None = None, section: str | None = None,
             q: str | None = None, sort: str = "discount",
             page: int = Query(0, ge=0),
             price_min: int | None = Query(None, ge=0),
             price_max: int | None = Query(None, ge=0),
             only_discounts: bool = False, badge: str | None = None,
             conn=Depends(get_conn)):
    """УСІ товари (не лише знижки) — повний прайс-агрегатор. `only_discounts=1` → лише
    знижкові; `badge=verified` → лише зі знижками, що пройшли перевірку 30-денним
    мінімумом (вкл. provisional на неповному вікні); `badge=pumped` → лише ті, де
    «стара» ціна вища за фактичний 30-денний мінімум."""
    _check_badge(badge); _check_section(section)
    return qdb.list_products(conn, category, sort, limit=50, offset=page * 50, q=q,
                             section=section,
                             price_min=price_min, price_max=price_max,
                             only_discounts=only_discounts, badge=badge)


@app.get("/api/freshness")
def api_freshness(conn=Depends(get_conn)):
    """Хвилини від останнього успішного збору — чесна свіжість даних у шапці стрічки."""
    return qdb.freshness(conn)


@app.get("/api/compare")
def compare(ids: str, conn=Depends(get_conn)):
    """Порівняння 2-4 товарів side-by-side (S14): базові факти + таблиця характеристик.
    `ids` — кома-розділені store_product_id (напр. ?ids=1,2,3)."""
    try:
        parsed = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "ids: кома-розділені цілі")
    if not 2 <= len(parsed) <= 4:
        raise HTTPException(400, "порівняння — від 2 до 4 товарів")
    return qdb.compare_products(conn, parsed)


@app.get("/api/product/{store_product_id}/card")
def product_card(store_product_id: int, conn=Depends(get_conn)):
    """Картка одного товару (S19) — для сторінки /product/{id}: назва, фото, ціна,
    бейдж перевірки, 30-денна база. `/offers` цього не дає й не має давати."""
    row = qdb.product_card(conn, store_product_id)
    if row is None:
        raise HTTPException(404, "товар не знайдено")
    return row


@app.get("/api/product/{store_product_id}/history")
def history(store_product_id: int, conn=Depends(get_conn)):
    return qdb.product_history(conn, store_product_id)


@app.get("/api/product/{store_product_id}/offers")
def offers(store_product_id: int, conn=Depends(get_conn)):
    """«Де купити» (T15): той самий товар (mpn) у всіх крамницях, від найдешевшої."""
    return qdb.product_offers(conn, store_product_id)


@app.get("/api/product/{store_product_id}/choice")
def choice(store_product_id: int, conn=Depends(get_conn)):
    """«Наш вибір» v1 (S9): найвигідніший спосіб купити — прозорий score поверх
    «Де купити» (ефективна ціна з доставкою-довідником + індекс чесності знижок
    із ВЛАСНИХ discount_event + самовивіз). ОКРЕМИЙ endpoint — /offers незмінний
    (сумісність MAUI). null = нема ≥2 in_stock-кандидатів (блок не показується)."""
    from choice.service import our_choice
    return {"choice": our_choice(conn, qdb.product_offers(conn, store_product_id))}


@app.get("/api/product/{store_product_id}/specs")
def specs(store_product_id: int, conn=Depends(get_conn)):
    """Характеристики (S12): пари назва-значення зі спец-таблиці картки крамниці —
    одна картка на крос-групу, віддається будь-якому члену групи. Завжди з
    провенансом (крамниця+URL+дата — інваріант B5). null = ще не зібрано."""
    return {"specs": qdb.product_specs(conn, store_product_id)}


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


def require_collector(authorization: str | None = Header(default=None),
                      conn=Depends(get_conn)):
    """Гейт ingest: статичний bearer-токен колектора (S10 — скрипти/GH Actions) АБО
    app-акаунт із роллю collector+ (S11 етап 3 — збір із застосунку). Повертає мітку
    колектора для провенансу (label токена або `acct:<user_id>`).

    Роль звіряємо з БАЗОЮ, не з токена (S16): інакше знижений або забанений колектор
    слав би дані далі — до кінця життя свого JWT."""
    label = qingest.collector_label(authorization)
    if label:
        return label
    claims = qauth.bearer_claims(authorization)
    if claims:
        u = qdb.get_user(conn, int(claims["sub"]))
        if u is not None and u.get("is_active", True) and u["role"] in _COLLECTOR_ROLES:
            return f"acct:{u['user_id']}"
    raise HTTPException(401, "потрібен токен колектора або акаунт із роллю collector")


# ── акаунти (S11): реєстрація / логін / профіль / watchlist на юзера ──────────────
def require_account(authorization: str | None = Header(default=None)):
    """Гейт для app-акаунтів: валідний JWT (api/auth). Повертає claims (sub, role).

    ⚠ РОЛЬ У CLAIMS — З МОМЕНТУ ВИДАЧІ ТОКЕНА, вона могла застаріти. Для будь-якого
    рішення про ПРАВА бери роль із бази (`_live_user` / require_moderator/admin),
    інакше зміна ролі не діятиме до перелогіну, а відібрати права буде неможливо."""
    claims = qauth.bearer_claims(authorization)
    if claims is None:
        raise HTTPException(401, "потрібен валідний токен акаунта")
    return claims


def require_active_account(claims=Depends(require_account), conn=Depends(get_conn)):
    """require_account + звірка, що акаунт живий і не забанений. Бан мусить діяти на
    ЧИННІ сесії теж — інакше «заблоковано» означало б лише «не зможе увійти знову»."""
    _live_user(claims, conn)
    return claims


def _live_user(claims, conn):
    """АКТУАЛЬНІ роль і стан акаунта — з БД, не з токена.

    Роль зашита в JWT на момент видачі, тож перевірка за claims має дві вади, і обидві
    ми зустріли живцем (2026-07-26): підвищений юзер не отримував прав до перелогіну, а
    ЗНИЖЕНИЙ адмін зберігав би повні права до кінця життя токена — тобто відібрати
    права було неможливо. Те саме з баном: він діяв лише на новий вхід.

    Ціна — один запит на адмін-виклик; ці ендпойнти й так ходять у базу."""
    u = qdb.get_user(conn, int(claims["sub"]))
    if u is None:
        raise HTTPException(401, "акаунт не існує")
    if not u.get("is_active", True):
        raise HTTPException(403, "акаунт заблоковано")
    return u


def require_moderator(claims=Depends(require_account), conn=Depends(get_conn)):
    """Гейт адмін-панелі (S15): role ∈ {moderator, admin}. Керування акаунтами + метрики.
    Повертає claims із ЖИВОЮ роллю — далі по коду вона вже звірена з базою."""
    u = _live_user(claims, conn)
    if u["role"] not in ("moderator", "admin"):
        raise HTTPException(403, "потрібні права модератора")
    return {"sub": u["user_id"], "role": u["role"]}


def require_admin(claims=Depends(require_account), conn=Depends(get_conn)):
    """Гейт зміни ролей (S15): лише admin. Найвищий рівень — роздача прав."""
    u = _live_user(claims, conn)
    if u["role"] != "admin":
        raise HTTPException(403, "потрібні права адміністратора")
    return {"sub": u["user_id"], "role": u["role"]}


def _rate_gate(request: Request, limiter: qrl.RateLimiter, limit: int, window: int):
    """429 із Retry-After, коли IP перевищив ліміт дорогого auth-ендпойнта."""
    ok, retry = limiter.check(qrl.client_ip(request), limit, window)
    if not ok:
        raise HTTPException(429, "Забагато спроб. Спробуй пізніше.",
                            headers={"Retry-After": str(retry)})


def _send_code(conn, user_id: int, email: str, kind: str):
    """Згенерувати одноразовий код, зберегти його ХЕШ, надіслати лист. Код у пошті —
    єдине місце plaintext. Збій листа не валить потік (email.send не кидає)."""
    code = qauth.make_code()
    ttl = qauth.VERIFY_TTL_S if kind == "verify" else qauth.RESET_TTL_S
    qdb.create_token(conn, user_id, kind, qauth.hash_code(code), ttl)
    subject, body = (qemail.verify_body(code) if kind == "verify" else qemail.reset_body(code))
    qemail.send(email, subject, body)


@app.post("/api/auth/register")
def register(body: dict, request: Request, conn=Depends(get_conn)):
    _rate_gate(request, qrl.register_limiter, qrl.REGISTER_LIMIT, qrl.REGISTER_WINDOW_S)
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
        token = qauth.make_token(user_id, role)     # SOFT-verify: вхід не блокуємо
    except qauth.AuthError as e:
        raise HTTPException(500, str(e))            # JWT_SECRET не заданий на сервері
    _send_code(conn, user_id, email, "verify")      # лист підтвердження (email_verified=false)
    return {"token": token, "role": role, "email": email, "email_verified": False}


@app.post("/api/auth/verify")
def verify_email(body: dict, request: Request, claims=Depends(require_active_account),
                 conn=Depends(get_conn)):
    """Підтвердити email кодом із листа. Прив'язано до залогіненого юзера."""
    _rate_gate(request, qrl.code_limiter, qrl.CODE_LIMIT, qrl.CODE_WINDOW_S)
    code = str((body or {}).get("code") or "").strip()
    if not code:
        raise HTTPException(400, "потрібен код")
    uid = int(claims["sub"])
    if not qdb.consume_token(conn, uid, "verify", qauth.hash_code(code)):
        raise HTTPException(400, "код невірний або протермінований")
    qdb.set_email_verified(conn, uid)
    return {"email_verified": True}


@app.post("/api/auth/verify/resend")
def verify_resend(request: Request, claims=Depends(require_active_account), conn=Depends(get_conn)):
    """Надіслати новий код підтвердження (якщо email ще не підтверджено)."""
    _rate_gate(request, qrl.email_limiter, qrl.EMAIL_LIMIT, qrl.EMAIL_WINDOW_S)
    u = qdb.get_user(conn, int(claims["sub"]))
    if u is None:
        raise HTTPException(401, "акаунт не існує")
    if u["email_verified"]:
        return {"email_verified": True}            # уже підтверджено — нема що слати
    _send_code(conn, u["user_id"], u["email"], "verify")
    return {"sent": True}


@app.post("/api/auth/reset/request")
def reset_request(body: dict, request: Request, conn=Depends(get_conn)):
    """«Забув пароль»: надіслати код на email. ЗАВЖДИ 200 — не розкриваємо, чи такий
    email зареєстрований (проти enumeration)."""
    _rate_gate(request, qrl.email_limiter, qrl.EMAIL_LIMIT, qrl.EMAIL_WINDOW_S)
    email = (body.get("email") or "").strip().lower()
    u = qdb.get_user_by_email(conn, email) if _EMAIL_RE.match(email) else None
    if u is not None:
        _send_code(conn, u["user_id"], u["email"], "reset")
    return {"ok": True}                             # однакова відповідь у будь-якому разі


@app.post("/api/auth/reset/confirm")
def reset_confirm(body: dict, request: Request, conn=Depends(get_conn)):
    """Змінити пароль за кодом із листа. Код прив'язаний до email; успіх гасить усі
    reset-токени юзера (update_password)."""
    _rate_gate(request, qrl.code_limiter, qrl.CODE_LIMIT, qrl.CODE_WINDOW_S)
    email = (body.get("email") or "").strip().lower()
    code = str(body.get("code") or "").strip()
    new_password = body.get("new_password") or ""
    if len(new_password) < qauth.MIN_PASSWORD:
        raise HTTPException(400, f"пароль ≥ {qauth.MIN_PASSWORD} символів")
    u = qdb.get_user_by_email(conn, email) if _EMAIL_RE.match(email) else None
    if u is None or not qdb.consume_token(conn, u["user_id"], "reset", qauth.hash_code(code)):
        raise HTTPException(400, "код невірний або протермінований")
    qdb.update_password(conn, u["user_id"], qauth.hash_password(new_password))
    return {"ok": True}


@app.post("/api/auth/login")
def login(body: dict, request: Request, conn=Depends(get_conn)):
    _rate_gate(request, qrl.login_limiter, qrl.LOGIN_LIMIT, qrl.LOGIN_WINDOW_S)
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    u = qdb.get_user_by_email(conn, email)
    # constant-ish: перевіряємо пароль навіть якщо юзера нема (проти user-enumeration за таймінгом)
    ok = u is not None and qauth.verify_password(password, u["password_hash"])
    if not ok:
        raise HTTPException(401, "невірний email або пароль")
    if not u.get("is_active", True):                 # забанений акаунт (S15)
        raise HTTPException(403, "акаунт заблоковано")
    qdb.touch_login(conn, u["user_id"])
    try:
        return {"token": qauth.make_token(u["user_id"], u["role"]),
                "role": u["role"], "email": u["email"],
                "email_verified": u["email_verified"]}
    except qauth.AuthError as e:
        raise HTTPException(500, str(e))


@app.get("/api/me")
def me(claims=Depends(require_active_account), conn=Depends(get_conn)):
    u = qdb.get_user(conn, int(claims["sub"]))
    if u is None:
        raise HTTPException(401, "акаунт не існує")
    return u


@app.get("/api/me/watchlist")
def my_watchlist(claims=Depends(require_active_account), conn=Depends(get_conn)):
    return qdb.list_watchlist_user(conn, int(claims["sub"]))


@app.post("/api/me/watchlist")
def my_watchlist_add(body: dict, claims=Depends(require_active_account), conn=Depends(get_conn)):
    kind = body.get("kind")
    if kind not in ("category", "store_product", "query"):
        raise HTTPException(400, "kind ∈ category|store_product|query")
    ref_id = body.get("ref_id")
    if kind == "store_product" and not isinstance(ref_id, int):
        raise HTTPException(400, "ref_id обовʼязковий для store_product")
    return qdb.add_watchlist_user(conn, int(claims["sub"]), kind,
                                  ref_id, body.get("query_text"))


@app.get("/api/me/watchlist/drops")
def my_price_drops(claims=Depends(require_active_account), conn=Depends(get_conn)):
    """Відстежувані товари, що подешевшали від часу останнього сповіщення.
    Застосунок опитує це у фоні й показує ЛОКАЛЬНЕ сповіщення (без сторонніх
    push-сервісів — §7.7: жодної телеметрії назовні)."""
    return qdb.list_price_drops(conn, int(claims["sub"]))


@app.post("/api/me/watchlist/drops/ack")
def my_price_drops_ack(body: dict, claims=Depends(require_active_account), conn=Depends(get_conn)):
    """Підтвердити, що про зниження повідомлено — щоб не дзвонити вдруге про те саме."""
    ids = (body or {}).get("watchlist_ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise HTTPException(400, "watchlist_ids: список int")
    return {"acked": qdb.ack_price_drops(conn, int(claims["sub"]), ids)}


@app.get("/api/me/watchlist/category-news")
def my_category_news(claims=Depends(require_active_account), conn=Depends(get_conn)):
    """Відстежувані КАТЕГОРІЇ з новими знижками від останнього сповіщення — одне
    згруповане сповіщення на категорію («N нових знижок, топ −X%»), не спам."""
    return qdb.list_category_news(conn, int(claims["sub"]))


@app.post("/api/me/watchlist/category-news/ack")
def my_category_news_ack(body: dict, claims=Depends(require_active_account), conn=Depends(get_conn)):
    """Підтвердити показ категорійних новин — водяний знак пересувається на now()."""
    ids = (body or {}).get("watchlist_ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise HTTPException(400, "watchlist_ids: список int")
    return {"acked": qdb.ack_category_news(conn, int(claims["sub"]), ids)}


@app.delete("/api/me/watchlist/{watchlist_id}")
def my_watchlist_remove(watchlist_id: int, claims=Depends(require_active_account),
                        conn=Depends(get_conn)):
    """Прибрати зі стеження. Чужий рядок не видалиться (user_id у WHERE) → 404."""
    if not qdb.remove_watchlist_user(conn, int(claims["sub"]), watchlist_id):
        raise HTTPException(404, "нема такого запису")
    return {"ok": True}


# ── адмін-панель (S15): керування акаунтами / ролі / метрики ──────────────────────
@app.get("/api/admin/users")
def admin_users(q: str | None = None, role: str | None = None,
                active: bool | None = None, page: int = 0,
                claims=Depends(require_moderator), conn=Depends(get_conn)):
    """Сторінка акаунтів (moderator+): пошук за email, фільтри роль/стан, пагінація.
    Без пагінації список ріс би без межі — панель мусить лишатись робочою на тисячах."""
    if role is not None and role not in qdb._ROLES:
        raise HTTPException(400, "невідома роль")
    return qdb.list_users(conn, q=q, role=role, active=active, page=page)


@app.get("/api/admin/metrics")
def admin_metrics(claims=Depends(require_moderator), conn=Depends(get_conn)):
    """Метрики панелі (moderator+): дані · детекція · збір по крамницях · акаунти.
    Стан черги домішуємо з qtasks.collect_health — щоб не заводити ДРУГЕ визначення
    «збір живий» поруч із наявним (розбіжні визначення показників гірші за їх брак)."""
    m = qdb.admin_metrics(conn)
    m["collect"]["health"] = qtasks.collect_health(conn)
    return m


@app.get("/api/admin/users/{user_id}")
def admin_user_detail(user_id: int, claims=Depends(require_moderator), conn=Depends(get_conn)):
    """Картка акаунта (moderator+): профіль + стеження + адмін-дії НАД НИМ."""
    u = qdb.user_detail(conn, user_id)
    if u is None:
        raise HTTPException(404, "акаунт не існує")
    return u


@app.get("/api/admin/audit")
def admin_audit_log(action: str | None = None, page: int = 0,
                    claims=Depends(require_moderator), conn=Depends(get_conn)):
    """Журнал адмін-дій (moderator+): хто, що, кому, коли. До S16 слід писався, але
    прочитати його не було чим — перевірити роздачу прав було неможливо."""
    return qdb.list_audit(conn, action=action, page=page)


@app.post("/api/admin/users/{target_id}/verify")
def admin_verify(target_id: int, claims=Depends(require_moderator), conn=Depends(get_conn)):
    """Підтвердити email вручну (moderator+) — коли лист не доходить. Пишеться в аудит."""
    try:
        return qdb.admin_verify_email(conn, int(claims["sub"]), target_id)
    except qdb.AdminForbidden as e:
        raise HTTPException(403, str(e))
    except qdb.AdminError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{target_id}/send-reset")
def admin_send_reset(target_id: int, request: Request, claims=Depends(require_moderator),
                     conn=Depends(get_conn)):
    """Надіслати юзеру код скидання пароля (moderator+). Лист іде на ЧУЖУ адресу, тож
    під лімітом і в аудиті — інакше це готовий вектор розсилки чужими руками."""
    _rate_gate(request, qrl.email_limiter, qrl.EMAIL_LIMIT, qrl.EMAIL_WINDOW_S)
    u = qdb.get_user(conn, target_id)
    if u is None:
        raise HTTPException(404, "акаунт не існує")
    _send_code(conn, u["user_id"], u["email"], "reset")
    qdb.audit_action(conn, int(claims["sub"]), "send_reset", target_id,
                     "надіслано код скидання")
    return {"sent": True}


@app.delete("/api/admin/users/{target_id}")
def admin_delete_user(target_id: int, claims=Depends(require_admin), conn=Depends(get_conn)):
    """Видалити акаунт (ЛИШЕ admin) — незворотно, право на забуття. Слід у журналі
    лишається (0171: email збережено знімком), тож історія прав не зникає разом з ним."""
    try:
        return qdb.delete_user(conn, int(claims["sub"]), target_id)
    except qdb.AdminForbidden as e:
        raise HTTPException(403, str(e))
    except qdb.AdminError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{target_id}/role")
def admin_set_role(target_id: int, body: dict, claims=Depends(require_admin),
                   conn=Depends(get_conn)):
    """Змінити роль акаунта (ЛИШЕ admin). Захисти в qdb.set_user_role (не власна роль,
    не лишити систему без admin). Кожна зміна → admin_audit."""
    role = (body or {}).get("role")
    try:
        return qdb.set_user_role(conn, int(claims["sub"]), target_id, role)
    except qdb.AdminForbidden as e:
        raise HTTPException(403, str(e))
    except qdb.AdminError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{target_id}/ban")
def admin_set_active(target_id: int, body: dict, claims=Depends(require_moderator),
                     conn=Depends(get_conn)):
    """Бан/розбан акаунта (moderator+). moderator не чіпає admin/moderator; не себе;
    не останнього admin (захисти в qdb.set_user_active). → admin_audit."""
    active = (body or {}).get("active")
    if not isinstance(active, bool):
        raise HTTPException(400, "active: bool")
    try:
        return qdb.set_user_active(conn, int(claims["sub"]), claims.get("role"),
                                   target_id, active)
    except qdb.AdminForbidden as e:
        raise HTTPException(403, str(e))
    except qdb.AdminError as e:
        raise HTTPException(400, str(e))


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
    Порожньо = все зібрано нещодавно; телефон засинає до наступного опитування.

    `sources` — колектор оголошує, що ВМІЄ (S23). Колектори різні: телефон має WebView
    і резидентний IP; серверний завжди ввімкнений, але без WebView і з ДЦ-адресою,
    яку частина крамниць блокує. Без фільтра сервер брав би приречені задачі й псував
    би їм лічильник збоїв замість лишити телефону."""
    qtasks.seed_tasks(conn)                 # ледачий сів: нове в HTML_SOURCES → у черзі
    qtasks.seed_card_tasks(conn)            # дозований бекфіл специфікацій (S12); дешевий guard усередині
    qtasks.refresh_task_value(conn)         # цінність сторінок (0172); guard — раз на 6 год
    limit = (body or {}).get("limit", 3)
    if not isinstance(limit, int):
        raise HTTPException(400, "limit має бути int")
    sources = (body or {}).get("sources")
    if sources is not None and not (isinstance(sources, list)
                                    and all(isinstance(s, str) for s in sources)):
        raise HTTPException(400, "sources: список рядків або відсутній")
    return {"tasks": qtasks.lease_tasks(conn, collector, limit, sources=sources),
            "collector": collector}


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
    if result.get("kind") in ("hub", "sitemap") and result.get("discovered"):
        # лендинги/картки — в чергу: фонові колектори розберуть їх із 15-хв розльотом,
        # а кнопковий режим може дотягнути одразу (обидва шляхи співіснують).
        # sitemap-нащадки — рідший повтор (2880): їх багато (add.ua 186 при здатності
        # ~96/добу/крамницю), щоденний повтор не влазить і роздував би overdue сторожа.
        rep = (qtasks.SITEMAP_REPEAT_MIN if result["kind"] == "sitemap"
               else qtasks.PAGE_REPEAT_MIN)
        result["enqueued"] = qtasks.enqueue_pages(conn, source, result["discovered"],
                                                  repeat_min=rep)
    if result.get("kind") == "page" and result.get("accepted"):
        # None = конкурентний прохід уже біжить (advisory-лок) — свіжі снапшоти
        # добере наступний інгест; це не помилка (fix 2026-07-23, LockNotAvailable).
        result["events"] = detect_pass(conn)    # бейджі лише коли справді щось прийняли (§8.4)
    # «Тихий нуль» (2026-07-23): page-задача, з якої адаптер не видобув ЖОДНОЇ позиції —
    # збій збору (челендж-сторінка, staging-шелл, зламана розмітка), а не успіх. Раніше
    # закривалась ok і добу виглядала здоровою (клас Eldorado-провалу, впіймано на
    # першому render-зборі MasterZoo). Тепер — fail із бекофом і видимим статусом.
    # hub/sitemap не чіпаємо: там accepted=0 штатно (повертають discovered).
    # card (S12) — теж: 0 атрибутів = челендж/зламана розмітка → fail (задача
    # лишається з бекофом; ok видалив би її назавжди — див. complete_task).
    zero = result.get("kind") in ("page", "card") and not result.get("accepted")
    note = "0 позицій (тихий нуль)" if zero else None
    task_id = body.get("task_id")
    if isinstance(task_id, int):
        result["task_closed"] = qtasks.complete_task(conn, task_id, collector,
                                                     ok=not zero, note=note)
    else:
        # Без task_id — це ручний прохід «зібрати все» (ходить за планом, не за чергою).
        # Сторінку таки зібрано, тож закриваємо задачу за (source, url): інакше черга
        # перезбирала б її вдруге, а last_done_at показував би «ще не брали».
        result["task_closed"] = qtasks.complete_by_url(conn, source, url,
                                                       ok=not zero, note=note)
    result["collector"] = collector
    return result
