"""read-API + сервер Mini App (§8.10.1). FastAPI; клієнт без прямого доступу до БД.

BOT_TOKEN / DATABASE_URL — лише з env (Actions secret). Запуск локально:
  uvicorn api.main:app --reload
"""
from __future__ import annotations
import os
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, Response)
from starlette.exceptions import HTTPException as StarletteHTTPException

import re

from db.pool import get_pool
from api import db as qdb
from api import ingest as qingest
from api import qtasks
from api import auth as qauth
from api import ratelimit as qrl
from api import email as qemail
from api import seo as qseo
from api.initdata import verify_init_data, check_auth_age, InitDataError
from detection.runner import detect_pass
from taxonomy import SECTION_ORDER, glyph_key
import merkle

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Радар знижок — read-API")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
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


# ── сторінки ────────────────────────────────────────────────────────────────────
# Прев'ю посилань і structured data збираються НА СЕРВЕРІ (api/seo.py): бот Telegram
# чи Facebook не виконує JS, тож усе, що малює клієнт, для нього не існує. Кожна
# сторінка має маркер `<!--SEO-->` у <head>, який ми заміщаємо готовим блоком.
_SEO_MARK = "<!--SEO-->"
_SUMMARY_MARK = "<!--SUMMARY-->"

# title / опис / noindex для сторінок без даних із БД
_META = {
    "index":   ("Хапай — знижки, перевірені історією цін",
                "Звіряємо заявлену знижку з нашою власною історією спостережень за ціною "
                "в українських крамницях: видно, чи ціна справді нижча, ніж була.", False),
    "catalog": ("Знижки в українських крамницях — Хапай",
                "Знижки, звірені з історією цін: найменша ціна за 30 днів проти того, що "
                "крамниця називає «старою».", False),
    "drops":   ("Що подешевшало за добу — Хапай",
                "Товари, ціна яких знизилась за нашими власними вимірами — не за "
                "оголошенням крамниці. Різниця між двома спостереженнями.", False),
    "verify":  ("Як перевірити, що ми не переписуємо історію — Хапай",
                "Щоденна печатка спостережень: корінь Меркла й ланцюжок.", False),
    "how":     ("Як ми перевіряємо знижки — Хапай",
                "Що саме ми записуємо, як рахуємо найменшу ціну за 30 днів і чого "
                "НЕ стверджуємо. Метод, а не обіцянка.", False),
    "delete-account": ("Видалення акаунта — Хапай",
                "Як видалити акаунт «Хапай» і всі пов'язані дані — з сайту або з "
                "застосунку.", False),
    "model":   ("Модель — ціни в крамницях | Хапай",
                "Усі пропозиції однієї моделі поруч: де дешевше й що ми перевірили.", False),
    "compare": ("Порівняння товарів — Хапай",
                "Ціна, заявлена знижка й наша перевірка для 2-4 товарів поруч.", True),
    "login":   ("Вхід — Хапай", "Вхід і реєстрація в «Хапай».", True),
    "me":      ("Мій кабінет — Хапай", "Стеження за цінами й налаштування акаунта.", True),
    "admin":   ("Панель — Хапай", "Службова сторінка.", True),
    "privacy": ("Конфіденційність — Хапай", "Які дані збирає «Хапай» і навіщо.", False),
    "terms":   ("Умови користування — Хапай", "Умови користування сервісом «Хапай».", False),
    "support": ("Підтримка — Хапай", "Як звʼязатися з «Хапай».", False),
    "unsubscribe": ("Відмова від листів — Хапай", "Вимкнути листи про зниження цін.", True),
    "404":     ("Сторінку не знайдено — Хапай", "Такої сторінки немає.", True),
}


def _asset_stamp() -> str:
    """Мітка версії статики = найсвіжіший mtime серед css/js.

    Навіщо, якщо є `Cache-Control: no-cache`. Заголовок діє лише на НОВІ відповіді —
    копія, збережена браузером ДО його появи, живе за евристикою й далі. Саме на це я
    двічі наступив, перевіряючи власні правки: сторінка приїжджала нова, стилі й
    скрипти лишались старі. Мітка в адресі робить стару копію просто іншим ресурсом,
    тож жодного «нова розмітка + старий код» більше не буває — ні в мене, ні в людей,
    які відкривали сайт учора.

    Рахуємо на кожен запит: три `stat()` дешевші за клас помилок, який вони знімають,
    а перерахунок на старті процесу давав би стару мітку після `git pull` без рестарту."""
    try:
        return str(max(int(os.path.getmtime(os.path.join(WEB_DIR, n))) for n in _ASSETS))
    except OSError:
        return "0"


def _page(name: str, head: str, summary: str = "", status: int = 200) -> HTMLResponse:
    """Готовий HTML із підставленим блоком <head>. Якщо маркера немає — віддаємо як є:
    сторінка без прев'ю краща за сторінку з винятком."""
    with open(os.path.join(WEB_DIR, f"{name}.html"), encoding="utf-8") as f:
        src = f.read()
    src = src.replace(_SEO_MARK, head, 1)
    if summary:
        src = src.replace(_SUMMARY_MARK, summary, 1)
    stamp = _asset_stamp()
    for a in _ASSETS:
        src = src.replace(f'"/s/{a}"', f'"/s/{a}?v={stamp}"')
    return HTMLResponse(src, status_code=status, headers=_NOCACHE)


def _static_page(name: str, path: str) -> HTMLResponse:
    title, desc, noindex = _META[name]
    return _page(name, qseo.page_head(title, desc, path, noindex=noindex))


@app.get("/")
def index():
    return _static_page("index", "/")


@app.get("/admin")
def admin_page():
    """Веб-панель (S16). Реєструється ДО catch-all `/{page}` — інакше той перехопив би
    шлях і віддав 404. Сторінка статична й без секретів: усі дані тягне через ті самі
    гейтовані /api/admin/*, токен бере з логіну й тримає в sessionStorage."""
    return _static_page("admin", "/admin")


# Сторінки сайту (S19). Кожна — окремий файл у web/; спільні стилі й скрипти лежать
# поруч і віддаються через /s/<файл>. УСІ ці маршрути мусять стояти ДО catch-all
# `/{page}` — інакше він перехопить шлях і віддасть 404 (на це вже наступали з /admin).
_PAGES = {"login", "me", "compare", "how", "delete-account", "drops"}
# ⚠ "catalog" зник із цього набору навмисно: у нього тепер ВЛАСНИЙ маршрут
# нижче, бо заголовок і canonical залежать від фільтра в адресі.
# Білий список: жодного обходу шляхом. Зображення — ВЛАСНА брендова графіка
# (scripts/make-brand-assets.py), не чужі фото: інваріант B не порушено.
_ASSETS = {"app.css": "text/css; charset=utf-8",
           "app.js": "application/javascript; charset=utf-8",
           "catalog.js": "application/javascript; charset=utf-8",
           "og.png": "image/png",
           "icon-32.png": "image/png",
           "icon-180.png": "image/png",
           "favicon.ico": "image/x-icon"}

# HTML і стилі їдуть у деплої РАЗОМ, а кешуються нарізно. FileResponse ставить лише
# ETag/Last-Modified, без Cache-Control, — і браузер застосовує евристичне кешування
# (частку від віку файлу). Наслідок бачив на собі 2026-07-27: після деплою сторінка
# приїхала НОВА, а app.css лишився старий, тобто нова розмітка малювалась старими
# правилами. `no-cache` не забороняє кеш — він вимагає ЩОРАЗУ перепитати; при збігу
# ETag відповідь буде 304 без тіла. Три файли, ціна — один умовний запит.
_NOCACHE = {"Cache-Control": "no-cache"}


@app.get("/s/{name}")
def asset(name: str):
    """Спільні стилі/скрипти/іконки. Список статичний — «..» чи будь-що інше не збігається."""
    kind = _ASSETS.get(name)
    if kind is None:
        raise HTTPException(404, "не знайдено")
    return FileResponse(os.path.join(WEB_DIR, name), media_type=kind, headers=_NOCACHE)


@app.get("/favicon.ico")
def favicon():
    """Окремим маршрутом: браузер просить саме /favicon.ico, а не /s/favicon.ico."""
    return FileResponse(os.path.join(WEB_DIR, "favicon.ico"), media_type="image/x-icon")


@app.get("/robots.txt")
def robots():
    return PlainTextResponse(qseo.ROBOTS, headers=_NOCACHE)


# Мапа сайту велика (десятки тисяч URL) і за годину майже не змінюється — збирати її
# на кожен запит краулера марно.
_SITEMAP = qseo.Cached(ttl_s=3600)


@app.get("/sitemap.xml")
def sitemap(conn=Depends(get_conn)):
    def build():
        cats, prods, models = qdb.sitemap_rows(conn)
        stores = [r["slug"] for r in qdb.store_list(conn)]
        return qseo.sitemap(cats, prods, stores, models)
    return Response(_SITEMAP.get(build), media_type="application/xml", headers=_NOCACHE)


@app.get("/.well-known/assetlinks.json")
def assetlinks():
    """Android App Links: без цього файлу посилання hapay.today НЕ відкриє застосунок
    (Android 12+ не питає користувача — мовчки веде в браузер). Відбиток підпису дає
    лише той, у кого ключ, тобто оператор; поки змінної немає — чесний 404, а не
    порожній файл, який виглядав би налаштованим."""
    fp = os.environ.get("ANDROID_CERT_SHA256", "").strip()
    if not fp:
        raise HTTPException(404, "не налаштовано")
    return JSONResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {"namespace": "android_app", "package_name": "com.companyname.hapay",
                   "sha256_cert_fingerprints": [f.strip() for f in fp.split(",") if f.strip()]},
    }], headers=_NOCACHE)


@app.get("/catalog")
def catalog_page(request: Request, conn=Depends(get_conn)):
    """Каталог. Заголовок і canonical залежать від фільтра в АДРЕСІ.

    ⚠ До 2026-07-27 усе `?c=…`, `?s=…`, `?b=…` віддавало один заголовок і canonical на
    `/catalog`. Тобто sitemap перелічував 148 категорійних адрес, кожна з яких сама
    казала краулеру «я копія, індексуй іншу» — гірше, ніж не перелічувати їх узагалі."""
    q = request.query_params
    cat = q.get("c") or None
    meta = qdb.category_meta(conn, cat) if cat else None
    section = q.get("s") if not meta else None
    if section is not None and section not in SECTION_ORDER:
        section = None                      # чужий розділ не отримує власного обличчя
    head = qseo.catalog_head(category=meta, section=section,
                             badge=q.get("b"), query=q.get("q"))
    return _page("catalog", head)


@app.get("/verify")
def verify_page(conn=Depends(get_conn)):
    return _page("verify", qseo.page_head(
        "Як перевірити, що ми не переписуємо історію — Хапай",
        "Щоденна печатка спостережень: корінь Меркла й ланцюжок. Будь-хто може "
        "перевірити окремий вимір, не вірячи нам на слово.", "/verify"))


@app.get("/stores")
def stores_page():          # список тягне клієнт через /api/stores — з'єднання тут зайве
    title = "Крамниці, за якими ми стежимо — Хапай"
    desc = ("Перелік українських крамниць, чиї ціни ми записуємо щодня, з кількістю "
            "знижок і перевірок. Лише факти спостережень.")
    return _page("stores", qseo.page_head(title, desc, "/stores"))


@app.get("/store/{slug}")
def store_page(slug: str, conn=Depends(get_conn)):
    st = qdb.store_meta(conn, slug.lower())
    if st is None:
        return _page("store", qseo.page_head("Крамницю не знайдено — Хапай",
                                             "Такої крамниці ми не відстежуємо.",
                                             f"/store/{slug}", noindex=True), status=404)
    return _page("store", qseo.store_head(st))


@app.get("/api/drops")
def api_drops(days: int = Query(1, ge=1, le=30), page: int = Query(0, ge=0),
              order: str = Query("fresh"), conn=Depends(get_conn)):
    """Що ПОДЕШЕВШАЛО за нашими вимірами (S28).

    Не плутати з `/api/discounts`: там знижки, ЗАЯВЛЕНІ крамницями. Тут — різниця між
    двома нашими вимірами, тобто єдине твердження продукту, яке неможливо намалювати."""
    if order not in qdb._DROP_ORDER:
        raise HTTPException(400, f"order ∈ {', '.join(qdb._DROP_ORDER)}")
    return {"summary": qdb.price_moves_summary(conn, days),
            "items": qdb.price_drops(conn, days, limit=50, offset=page * 50, order=order),
            "days": days, "order": order}


@app.get("/api/model/{product_id}")
def api_model(product_id: int, conn=Depends(get_conn)):
    """Канонічна МОДЕЛЬ: усі сторінки крамниць під одним артикулом (S30).

    ⚠ Бейджі тут ПОСТОРІНКОВІ й такими лишаються: закон говорить про мінімум за
    30 днів у ЦЬОГО продавця, тож «модельного» вердикту не існує."""
    m = qdb.model_card(conn, product_id)
    if m is None:
        raise HTTPException(404, "модель не знайдено")
    return m


@app.get("/api/market")
def api_market(days: int = Query(30, ge=1, le=365), conn=Depends(get_conn)):
    """Ринковий зріз: скільки заявлених знижок ми змогли перевірити (S31).

    ⚠ `confident=false` означає «вибірки замало для висновку» — і клієнти зобовʼязані
    в цьому разі показувати сирі лічильники без відсотка. Опублікувати «половина знижок
    накачані» на вибірці 116 було б рівно тією накачаною знижкою, яку ми ловимо."""
    return qdb.market_index(conn, days)


@app.get("/api/verify")
def api_verify(conn=Depends(get_conn)):
    """Печатки діб: корінь Меркла + ланцюжок (S31).

    Це і є «доказ замість обіцянки»: підміна однієї ціни заднім числом змінює корінь
    її доби й ламає всі наступні ланки ланцюжка."""
    return {"format": "merkle-sha256-v1", "seals": qdb.seals(conn)}


@app.get("/api/verify/proof/{price_snapshot_id}")
def api_verify_proof(price_snapshot_id: int, conn=Depends(get_conn)):
    """Доказ на ОДИН вимір: лист, шлях до кореня й сам корінь.

    Сенс саме в цьому: людина перевіряє одну ціну, яку бачить в історії товару, не
    отримуючи від нас решти бази й не вірячи нам на слово."""
    snap = qdb.snapshot_for_proof(conn, price_snapshot_id)
    if snap is None:
        raise HTTPException(404, "виміру не існує")
    day = snap["day"].isoformat()
    seal = qdb.seal_of_day(conn, day)
    if seal is None:
        raise HTTPException(409, f"добу {day} ще не запечатано (печатка ставиться після її кінця)")
    rows = qdb.day_rows(conn, day)
    leaves = [merkle.leaf(r["store_product_id"], r["price_now_kop"], r["price_old_kop"],
                          r["in_stock"], r["seen_at"]) for r in rows]
    try:
        idx = next(i for i, r in enumerate(rows)
                   if r["price_snapshot_id"] == price_snapshot_id)
    except StopIteration:
        raise HTTPException(500, "вимір не потрапив у добу — це помилка на нашому боці")
    return {
        "format": "merkle-sha256-v1",
        "day": day,
        "observation": {
            "store_product_id": snap["store_product_id"],
            "price_now_kop": snap["price_now_kop"],
            "price_old_kop": snap["price_old_kop"],
            "in_stock": snap["in_stock"],
            "seen_at": snap["seen_at"].isoformat(),
        },
        "leaf": leaves[idx],
        "path": merkle.proof(leaves, idx),
        "merkle_root": seal["merkle_root"],
        "chain": seal["chain"],
    }


@app.get("/api/stores")
def api_stores(conn=Depends(get_conn)):
    return qdb.store_list(conn)


@app.get("/api/store/{slug}")
def api_store(slug: str, conn=Depends(get_conn)):
    st = qdb.store_meta(conn, slug.lower())
    if st is None:
        raise HTTPException(404, "крамницю не знайдено")
    return st


@app.get("/model/{product_id}")
def model_page(product_id: int, conn=Depends(get_conn)):
    m = qdb.model_card(conn, product_id)
    if m is None:
        return _page("model", qseo.page_head("Модель не знайдено — Хапай",
                                             "Такої моделі ми не відстежуємо.",
                                             f"/model/{product_id}", noindex=True), status=404)
    return _page("model", qseo.model_head(m), qseo.model_summary(m))


@app.get("/product/{store_product_id}")
def product_page(store_product_id: int, conn=Depends(get_conn)):
    """Сторінка товару окремим URL — щоб на неї можна було послатись і поділитись.

    Прев'ю й JSON-LD збираємо ТУТ: бот, який будує картку посилання в чаті, JS не
    виконує, тож усе намальоване клієнтом для нього не існує. Заразом кладемо в
    розмітку назву й ціну — сторінка приїжджає не порожньою."""
    card = qdb.product_card(conn, store_product_id)
    if card is None:                       # неіснуючий товар не має потрапляти в індекс
        return _page("product", qseo.page_head("Товар не знайдено — Хапай",
                                               "Такого товару в нас немає.",
                                               f"/product/{store_product_id}", noindex=True))
    return _page("product", qseo.product_head(card), qseo.product_summary(card))


@app.get("/unsubscribe")
def unsubscribe_page(u: int = 0, s: str = "", conn=Depends(get_conn)):
    """Відмова від листів ОДНИМ КЛІКОМ, без входу.

    Людина, яка хоче припинити листи, не повинна згадувати пароль — інакше наступний
    крок не «відписатись», а «поскаржитись на спам». Підпис HMAC від JWT_SECRET:
    жодної нової колонки, а посилання не підробити й воно гасне з ротацією секрету."""
    ok = u > 0 and s and qauth.verify_unsub(u, s)
    if ok:
        qdb.set_email_alerts(conn, u, False)
    title = "Листи вимкнено — Хапай" if ok else "Посилання недійсне — Хапай"
    return _page("unsubscribe", qseo.page_head(title, "Відмова від листів про ціни.",
                                               "/unsubscribe", noindex=True),
                 summary="ok" if ok else "bad")


@app.get("/{page}")
def legal(page: str):
    """Сторінки сайту (S19) + юр-сторінки /privacy, /terms, /support (вимога сторів)."""
    if page not in _PAGES and page not in _LEGAL:
        raise HTTPException(404, "не знайдено")
    return _static_page(page, f"/{page}")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    """404 для ЛЮДИНИ мусить бути сторінкою, а не `{"detail":"не знайдено"}`.

    До 2026-07-27 будь-яка одруківка в адресі чи стале посилання віддавали сирий JSON
    із `application/json` — тобто браузер показував рядок коду. Розрізняємо за тим, чого
    просить клієнт: `Accept: text/html` і шлях поза /api — сторінка; усе інше (застосунок,
    fetch зі сторінки, curl) — як було, JSON, бо на нього там і чекають."""
    wants_html = "text/html" in (request.headers.get("accept") or "")
    if exc.status_code == 404 and wants_html and not request.url.path.startswith("/api/"):
        title, desc, noindex = _META["404"]
        return _page("404", qseo.page_head(title, desc, "/404", noindex=noindex), status=404)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


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


def _attach_visuals(conn, rows) -> None:
    """Мікрографік історії + гліф розділу для стрічок обох клієнтів (S32/S33).

    ⚠ Спільна функція, а не копія в кожному ендпойнті, з дорогої причини: у S32 я
    додав це ЛИШЕ в `/api/discounts`, вирішивши з памʼяті, що застосунок ходить
    туди. Він ходить у `/api/products` — тобто в застосунку байндинги дивились у
    порожнечу, і збірка про це мовчала, бо відсутнє поле JSON — не помилка.

    `spark` — один запит на всю сторінку, не 50. Товари з надто короткою історією
    сюди не потрапляють: клієнт малює графік лише там, де є що малювати.
    `glyph` — ключ вектора для плитки БЕЗ фото; розділ живе лише в taxonomy (у БД
    його нема), тож рахуємо там, інакше сайт і застосунок групували б однакові
    товари під різними значками.
    """
    if not rows:
        return
    series = qdb.spark_series(conn, [r["store_product_id"] for r in rows])
    for r in rows:
        r["spark"] = series.get(r["store_product_id"], [])
        r["glyph"] = glyph_key(r.get("category_slug") or "")


@app.get("/api/discounts")
def discounts(category: str | None = None, section: str | None = None,
              badge: str | None = None, q: str | None = None,
              sort: str = "verified", page: int = Query(0, ge=0),
              price_min: int | None = Query(None, ge=0),   # копійки (інв. A); фільтр за поточною ціною
              price_max: int | None = Query(None, ge=0),
              conn=Depends(get_conn)):
    _check_badge(badge); _check_section(section)
    rows = qdb.list_discounts(conn, category, badge, sort, limit=50, offset=page * 50, q=q,
                              price_min=price_min, price_max=price_max, section=section)
    _attach_visuals(conn, rows)
    return rows


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
    rows = qdb.list_products(conn, category, sort, limit=50, offset=page * 50, q=q,
                             section=section,
                             price_min=price_min, price_max=price_max,
                             only_discounts=only_discounts, badge=badge)
    _attach_visuals(conn, rows)
    return rows


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


@app.get("/api/product/{store_product_id}/low")
def product_low(store_product_id: int, conn=Depends(get_conn)):
    """Найнижча ціна ЗА ЧАС НАШИХ СПОСТЕРЕЖЕНЬ.

    ⚠ Віддаємо не лише число, а й вікно (`days`, `first_day`, `measurements`) — і
    клієнти зобовʼязані його показувати. «Найнижча за весь час» при історії з 18.07
    було б самообманом того самого сорту, який ми ловимо в крамниць: твердження без
    власного вікна не перевірити. `is_low` = поточна ціна дорівнює цьому мінімуму."""
    row = qdb.historical_low(conn, store_product_id)
    if row is None or row.get("low_kop") is None:
        raise HTTPException(404, "історії ще немає")
    return row


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
    # ⚠ ВІДПОВІДЬ ОДНАКОВА В ОБОХ ВИПАДКАХ (T20 переглянуто 2026-07-27).
    # Доти дубль давав 409, тобто будь-хто міг перевірити, чи є в нас акаунт на чужу
    # адресу — біт, який годиться для прицільного фішингу й для відсіву адрес перед
    # credential stuffing. Тепер і код, і тіло, і факт відправки листа однакові;
    # різниця лише в тому, ЩО прийде на пошту — а це бачить тільки її власник.
    #
    # Токен більше НЕ повертаємо: віддати сесію одразу означало б відрізнити «створено»
    # від «уже було» саме її наявністю. Людина входить звичайним логіном тим паролем,
    # який щойно ввела, і підтверджує пошту з кабінету.
    row = qdb.create_user(conn, email, qauth.hash_password(password))
    if row is None:
        # адреса вже зареєстрована: повідомляємо ВЛАСНИКА (без коду — код тут був би
        # вектором, а не захистом) і мовчимо тому, хто натиснув «зареєструватись»
        subject, text = qemail.signup_attempt_body()
        qemail.send(email, subject, text)
    else:
        _send_code(conn, row[0], email, "verify")   # лист підтвердження новому акаунту
    return {"sent": True}


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
    # Хеш рахуємо ЗАВЖДИ — і для неіснуючого email теж, проти пари за таймінгом.
    # ⚠ Тут довго стояв коментар, що так і робиться, а код був
    # `u is not None and verify_password(...)`: `and` коротко замикається, тож для
    # неіснуючого юзера pbkdf2 не викликався взагалі. Заміряно на живому 2026-07-27:
    # 245 мс проти 421 — «чи є акаунт» читалось із таймінгу. Порядок важливий:
    # спершу хеш, і лише потім перевірка на None.
    ok = qauth.verify_password(password, u["password_hash"] if u else qauth.DUMMY_HASH)
    ok = ok and u is not None
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


@app.delete("/api/me")
def delete_me(claims=Depends(require_active_account), conn=Depends(get_conn)):
    """Самостійне видалення акаунта.

    Вимога Google Play (перевірено у першоджерелі 2026-07-27): застосунок із
    реєстрацією мусить давати шлях видалення І в інтерфейсі, І окремою веб-адресою,
    доступною без встановлення. У нас не було ЖОДНОГО з двох — лише «напишіть на
    support@», тобто ручний процес, який політика не приймає.

    Незворотно: watchlist і токени підуть каскадом. Слід у журналі лишається (0171
    тримає знімок email) — інакше видалення акаунта стирало б і історію прав."""
    try:
        return qdb.delete_own_account(conn, int(claims["sub"]))
    except qdb.AdminError as e:
        raise HTTPException(400, str(e))


@app.get("/api/me/watchlist")
def my_watchlist(claims=Depends(require_active_account), conn=Depends(get_conn)):
    return qdb.list_watchlist_user(conn, int(claims["sub"]))


def _target_kop(body: dict) -> int | None:
    """Цільова ціна з тіла запиту. Копійки (інв. A) — клієнт переводить гривні сам,
    як і всюди. Нуль і відʼємне відкидаємо: «сповісти, коли буде 0 грн» — не намір,
    а помилка вводу."""
    raw = body.get("target_kop")
    if raw is None:
        return None
    if not isinstance(raw, int) or raw <= 0:
        raise HTTPException(400, "target_kop — ціле число копійок > 0")
    return raw


@app.post("/api/me/watchlist")
def my_watchlist_add(body: dict, claims=Depends(require_active_account), conn=Depends(get_conn)):
    kind = body.get("kind")
    if kind not in ("category", "store_product", "query"):
        raise HTTPException(400, "kind ∈ category|store_product|query")
    ref_id = body.get("ref_id")
    if kind == "store_product" and not isinstance(ref_id, int):
        raise HTTPException(400, "ref_id обовʼязковий для store_product")
    target = _target_kop(body)
    if kind == "query":
        # Стеження за запитом БЕЗ цілі — це не сповіщення, а розсилка: під слово
        # «навушники» підпадають тисячі товарів, і «будь-яке зниження» серед них
        # означало б лист щогодини. Ціль робить твердження перевірюваним.
        if not (body.get("query_text") or "").strip():
            raise HTTPException(400, "query_text обовʼязковий для query")
        if target is None:
            raise HTTPException(400, "для стеження за запитом потрібна цільова ціна")
    return qdb.add_watchlist_user(conn, int(claims["sub"]), kind,
                                  ref_id, body.get("query_text"), target)


@app.patch("/api/me/watchlist/{watchlist_id}")
def my_watchlist_target(watchlist_id: int, body: dict,
                        claims=Depends(require_active_account), conn=Depends(get_conn)):
    """Змінити цільову ціну. `target_kop: null` — прибрати ціль (будь-яке зниження)."""
    row = qdb.set_watch_target(conn, int(claims["sub"]), watchlist_id, _target_kop(body))
    if row is None:
        raise HTTPException(404, "запис не знайдено")
    return row


@app.post("/api/me/alerts")
def my_alerts_pref(body: dict, claims=Depends(require_active_account), conn=Depends(get_conn)):
    """Згода на листи про зниження цін."""
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(400, "enabled — true або false")
    if not qdb.set_email_alerts(conn, int(claims["sub"]), enabled):
        raise HTTPException(404, "акаунт не існує")
    return {"email_alerts": enabled}


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
