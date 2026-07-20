"""Distributed ingest (S10): довірені колектори шлють зібране на сервер.

Навіщо: наш ДЦ-IP (Hetzner) отримує 403 від Rozetka/Allo/Foxtrot/Moyo/... Довірені
колектори (оператор + друзі) збирають зі СВОЇХ резидентних мереж, зі згодою, і шлють
сюди. Це НЕ botnet: збирають ВЛАСНИКИ проекту, не несвідомі клієнти (§7.4/§7.7).

Два тверді правила (без них ingest = дірка в єдиному активі — базі):
  1. Автентифікація per-колектор — лише відомі bearer-токени (`INGEST_TOKENS`). Свій
     токен на кожного → витік одного відкликається окремо.
  2. Сервер ВАЛІДУЄ кожен елемент, не вірить на слово. Довіра до людини ≠ довіра до
     кожного байта (телефон можна зламати; база — єдиний актив). URL мусить бути на
     домені крамниці, ціна — у розумному діапазоні, назва — не порожня.
"""
from __future__ import annotations

import dataclasses
import hmac
import os
import re
from urllib.parse import urlsplit

from adapters.allo import HUB as ALLO_HUB, AlloAdapter
from adapters.base import RawItem, canon_ref
from adapters.brain import BrainAdapter
from adapters.citrus import CitrusAdapter
from adapters.comfy import ComfyAdapter
from adapters.eldorado import EldoradoAdapter
from adapters.foxtrot import FoxtrotAdapter
from adapters.ktc import KtcAdapter
from adapters.moyo import MoyoAdapter
from adapters.rozetka import RozetkaAdapter
from db.store import load_categories, persist_items, upsert_source

# ── Сервер — АВТОРИТЕТ, хто може бути джерелом і які хости валідні ────────────────
# Колектор не може «вигадати» джерело: лише ці назви приймаються, і URL кожного
# елемента мусить бути на дозволеному хості (проти інʼєкції чужих/фішинг-URL).
INGEST_SOURCES: dict[str, dict] = {
    "Foxtrot":  {"base_url": "https://www.foxtrot.com.ua", "hosts": ("foxtrot.com.ua",)},
    "Moyo":     {"base_url": "https://www.moyo.ua",        "hosts": ("moyo.ua",)},
    "Eldorado": {"base_url": "https://eldorado.ua",        "hosts": ("eldorado.ua",)},
    "Rozetka":  {"base_url": "https://rozetka.com.ua",     "hosts": ("rozetka.com.ua",)},
    "Allo":     {"base_url": "https://allo.ua",            "hosts": ("allo.ua",)},
    "Comfy":    {"base_url": "https://comfy.ua",           "hosts": ("comfy.ua",)},
    "Citrus":   {"base_url": "https://www.ctrs.com.ua",    "hosts": ("ctrs.com.ua",)},
    "Brain":    {"base_url": "https://brain.com.ua",       "hosts": ("brain.com.ua",)},
    "KTC":      {"base_url": "https://ktc.ua",             "hosts": ("ktc.ua",)},
}

# ── Серверний парсинг пересланого HTML (S11 етап 3) ───────────────────────────────
# Застосунок = «тупий фетчер»: тягне HTML зі своєї резидентної мережі й шле сюди, а
# ВСЯ екстракція — тут, на сервері. Плюс: зміна селекторів/крамниці не вимагає оновлення
# застосунку в сторах. Лише джерела з РОБОЧИМ серверним адаптером; host-політика — з
# INGEST_SOURCES вище. `hub` → дворівневий discovery (сервер робить discover, не застосунок).
HTML_SOURCES: dict[str, dict] = {
    # `category` — джерело-рівневий дефолт: hub-лендинги відкриваються динамічно,
    # їх не пре-тегувати поіменно, але весь Allo-хаб — смартфони.
    "Allo": {"adapter": AlloAdapter(), "hub": ALLO_HUB, "max_pages": 20,
             "category": "smartfony"},
    # Foxtrot/Moyo (2026-07-19): лістинги категорій SSR-лять картки з MPN у назвах —
    # база T15-матчингу. З ДЦ — 403, тому лише через колектора (резидентний IP).
    # Категорії = смартфони (перетин з Allo за MPN доведено розвідкою); сервер —
    # авторитет над списком: додати категорію = дописати URL тут.
    # Ноутбуки/ТВ (розвідка 2026-07-20): URL узято з НАВІГАЦІЇ крамниць (не вгадано —
    # вгадані лістинги раніше давали 404) і перевірено ПАРСИНГОМ адаптера, не лише 200.
    # `page_tpl`/`pages` — пагінація (розвідка 2026-07-20). Схеми взято з навігації
    # крамниць і перевірено фактом: сторінка 2 віддає ІНШІ товари, перетин з 1-ю = 0.
    # Глибина 10 теж перевірена: стор. 8/10/12 віддають повні набори без повторів 1-ї.
    # KTC — 7: далі його лістинги віддають порожньо (сенсу слати запит немає).
    # 174 задачі / 12 год ≈ 14.6 оренд/год, тому застосунок бере по 5 за прохід (20/год).
    "Foxtrot": {"adapter": FoxtrotAdapter(), "page_tpl": "{base}?page={n}", "pages": 10, "urls": (
        ("https://www.foxtrot.com.ua/uk/shop/mobilnye_telefony.html", "smartfony"),
        ("https://www.foxtrot.com.ua/uk/shop/noutbuki.html", "noutbuky"),        # 42 товари
        ("https://www.foxtrot.com.ua/uk/shop/led_televizory.html", "tv"),        # 42 товари
    )},
    "Moyo": {"adapter": MoyoAdapter(), "page_tpl": "{base}?page={n}", "pages": 10, "urls": (
        ("https://www.moyo.ua/ua/telecommunication/smart/", "smartfony"),
        ("https://www.moyo.ua/ua/comp-and-periphery/notebooks/", "noutbuky"),    # 24 товари
        ("https://www.moyo.ua/ua/foto_video/tv_audio/lcd_tv/", "tv"),            # 24 товари
    )},
    # Comfy (розвідка 2026-07-19): SSR-лістинг, 50 карток, MPN у назвах — перетин із
    # Allo/Foxtrot/Moyo (напр. SM-A376BLVGEUC) → групи «Де купити» ширшають.
    # Comfy → render (2026-07-20): почав віддавати анти-бот заглушку («Pardon Our
    # Interruption», 6 КБ, challenge) на ВСІ прості GET — навіть на смартфон-лістинг,
    # який доти працював. У СПРАВЖНЬОМУ браузері блоку немає (перевірено): сторінки
    # віддають по 50 карток, і всі 50 читаються нашими ж селекторами (product-tile-catalog
    # + .product-tile-title/.product-tile-price__current) — адаптер міняти не довелось.
    # Тому телефон рендерить Comfy у WebView, як Brain. Рендер ~1.9-2.4 МБ — під _MAX_HTML (5 МБ).
    "Comfy": {"adapter": ComfyAdapter(), "mode": "render",
              "page_tpl": "{base}?p={n}", "pages": 10, "urls": (
        ("https://comfy.ua/smartfon/", "smartfony"),
        ("https://comfy.ua/notebook/", "noutbuky"),                              # 50 карток
        ("https://comfy.ua/flat-tvs/", "tv"),                                    # 50 карток
    )},
    # Rozetka (розвідка 2026-07-19): найбільший маркетплейс, Angular-SSR 60 карток;
    # масові перетини MPN (SM-S942BZKGEUC = Foxtrot S26, SM-A576BZVDEUC = Moyo/Allo A57).
    "Rozetka": {"adapter": RozetkaAdapter(), "page_tpl": "{base}page={n}/", "pages": 10, "urls": (
        ("https://rozetka.com.ua/ua/mobile-phones/c80003/", "smartfony"),
        ("https://rozetka.com.ua/ua/notebooks/c80004/", "noutbuky"),             # 60 товарів
        ("https://rozetka.com.ua/ua/all-tv/c80037/", "tv"),                      # 60 товарів
    )},
    # Citrus (розвідка 2026-07-19): Next.js SSR, 47 карток, хешовані класи (префіксні
    # селектори); SM-S948BZKGEUC перетинається з Comfy → більше груп.
    "Citrus": {"adapter": CitrusAdapter(), "page_tpl": "{base}?page={n}", "pages": 10, "urls": (
        ("https://www.ctrs.com.ua/smartfony/", "smartfony"),
        ("https://www.ctrs.com.ua/noutbuki-i-ultrabuki/", "noutbuky"),           # 47 товарів
        ("https://www.ctrs.com.ua/televizory/", "tv"),                           # 47 товарів
    )},
    # Brain (розвідка 2026-07-19): SPA — ціни лише після JS → mode="render" (телефон
    # рендерить у WebView). Дані з data-атрибутів; A07 SM-A075FZKGSEK перетин із Moyo/Rozetka.
    # БЕЗ пагінації (перевірено 2026-07-20 у браузері): посилань на сторінки нема
    # (нескінченний скрол), `page=2/` → 404, `?page=2` → 200 але без товарів у HTML.
    # Потрібен скрол у WebView — окрема робота; поки лишається 1 сторінка на категорію.
    "Brain": {"adapter": BrainAdapter(), "mode": "render", "urls": (
        ("https://brain.com.ua/ukr/Smartfoni_zvyazok-c297/", "smartfony"),
        ("https://brain.com.ua/ukr/category/Noutbuky-c1191/", "noutbuky"),       # 24 товари
        ("https://brain.com.ua/ukr/category/Televizory-c1098/", "tv"),           # 24 товари
    )},
    # Eldorado (розвідка 2026-07-20, у справжньому браузері): SPA + ЛІНИВІ ціни — без
    # прокрутки сторінка віддає товари з НУЛЕМ цін, тому лише mode="render" і лише з
    # новим скрол-рендерером. URL узято з навігації (вгаданий /smartfony/c1050/ → сторінка
    # помилки). Перевірено парсингом: смартфони 32 картки / 11 із цінами (решта «Продано»
    # чи «Незабаром» — їх адаптер пропускає), ноутбуки 40/32, ТВ 40/40.
    # pages=5, а не 10: рендер-задачі найповільніші (скрол), а черга вже щільна —
    # підняти можна, коли побачимо запас (див. арифметику в коментарі до пагінації).
    "Eldorado": {"adapter": EldoradoAdapter(), "mode": "render",
                 "page_tpl": "{base}page={n}/", "pages": 5, "urls": (
        ("https://eldorado.ua/uk/smartphones/c1038946/", "smartfony"),
        ("https://eldorado.ua/uk/notebooks/c1039096/", "noutbuky"),
        ("https://eldorado.ua/uk/led/c1038962/", "tv"),
    )},
    # KTC (розвідка 2026-07-19): SSR-лістинг /smartphone/, 48 карток, 54 SM-коди —
    # S26/A07 перетини з рештою → більше груп «Де купити».
    "KTC": {"adapter": KtcAdapter(), "page_tpl": "{base}?page={n}", "pages": 7, "urls": (
        ("https://ktc.ua/smartphone/", "smartfony"),
        ("https://ktc.ua/notebook/", "noutbuky"),                                # 48 товарів
        ("https://ktc.ua/tv/", "tv"),                                            # 48 товарів
    )},
}
# режим збору per-source: 'fetch' (plain GET) | 'render' (WebView — SPA-крамниці).
COLLECT_MODE = {name: cfg.get("mode", "fetch") for name, cfg in HTML_SOURCES.items()}


def _url_cat(entry):
    """url-запис — рядок або (url, category_slug). → (url, slug|None)."""
    return (entry, None) if isinstance(entry, str) else (entry[0], entry[1])


def source_listings(cfg) -> list[tuple[str, str | None]]:
    """Усі лістинг-URL джерела з категоріями, ВКЛЮЧНО з пагінацією.

    Сторінки 2..N будуються за схемою самої крамниці (`page_tpl`), перевіреною фактом:
    сторінка 2 має віддавати ІНШІ товари (розвідка 2026-07-20 — перетин з 1-ю усюди 0).
    Категорія успадковується від першої сторінки, тож окремо її ніде реєструвати не треба.
    Джерело без `page_tpl` (SPA-крамниці на кшталт Brain) лишається з однією сторінкою.
    """
    out: list[tuple[str, str | None]] = []
    tpl, pages = cfg.get("page_tpl"), cfg.get("pages", 1)
    for entry in cfg.get("urls", ()):
        u, c = _url_cat(entry)
        out.append((u, c))
        if tpl:
            out += [(tpl.format(base=u, n=n), c) for n in range(2, pages + 1)]
    return out


# (source, url) → категорія: категорія береться з ЛІСТИНГА, який зібрали (надійно),
# а не вгадується з product-URL. Hub-лендинги (Allo) тут відсутні → падають на categorize().
URL_CATEGORY: dict[tuple[str, str], str] = {}
for _name, _cfg in HTML_SOURCES.items():
    for _u, _c in source_listings(_cfg):
        if _c:
            URL_CATEGORY[(_name, _u)] = _c

PRICE_MIN_KOP = 100                 # 1 грн — нижче майже напевно помилка парсингу
PRICE_MAX_KOP = 100_000_000         # 1 000 000 грн — стеля здорового глузду
_MAX_TITLE = 300
_MAX_REF = 500
_MAX_URL = 600
# 12 МБ на сторінку — стеля проти роздування (звичайні лендинги ~сотні КБ).
# Підняли з 5 МБ 2026-07-20: рендерер тепер ПРОКРУЧУЄ сторінку до стабілізації DOM,
# тож нескінченні стрічки (Brain) віддають помітно більший HTML, ніж перший екран.
_MAX_HTML = 12_000_000


def load_tokens() -> dict[str, str]:
    """token → label з env `INGEST_TOKENS` (формат: `label:token,label2:token2`).

    Токен генерувати `openssl rand -hex 32`; класти в /etc/hapay/hapay.env, НЕ в git.
    """
    raw = os.environ.get("INGEST_TOKENS", "").strip()
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        label, tok = pair.split(":", 1)
        label, tok = label.strip(), tok.strip()
        if label and tok:
            out[tok] = label
    return out


def collector_label(authorization: str | None) -> str | None:
    """Повертає label колектора для валідного `Authorization: Bearer <token>`, інакше None.
    Порівняння — constant-time (hmac.compare_digest) проти timing-атак."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    for known, label in load_tokens().items():
        if hmac.compare_digest(token, known):
            return label
    return None


def _host_ok(url: str, allowed: tuple[str, ...]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == a or host.endswith("." + a) for a in allowed)


def validate_item(source: str, raw: dict) -> tuple[RawItem | None, str | None]:
    """Один елемент від колектора → (RawItem, None) або (None, причина-відмови).

    Сервер НЕ вірить на слово навіть довіреному колектору: усе перевіряється тут.
    """
    hosts = INGEST_SOURCES[source]["hosts"]

    url = raw.get("url")
    if not isinstance(url, str) or not (0 < len(url) <= _MAX_URL):
        return None, "url: порожній/задовгий"
    if urlsplit(url).scheme != "https":
        return None, "url: лише https"
    if not _host_ok(url, hosts):
        return None, f"url не на домені {source} ({hosts})"

    title = raw.get("title")
    if not isinstance(title, str) or not (0 < len(title.strip()) <= _MAX_TITLE):
        return None, "title: порожній/задовгий"

    now = raw.get("price_now_kop")
    if not isinstance(now, int) or isinstance(now, bool) or not (PRICE_MIN_KOP <= now <= PRICE_MAX_KOP):
        return None, f"price_now_kop поза [{PRICE_MIN_KOP},{PRICE_MAX_KOP}]"

    old = raw.get("price_old_kop")
    if old is not None:
        if not isinstance(old, int) or isinstance(old, bool) or not (PRICE_MIN_KOP <= old <= PRICE_MAX_KOP):
            return None, "price_old_kop поза діапазоном"
        if old <= now:
            old = None                                  # «стара» не вища за поточну — не знижка

    ext = raw.get("external_ref")
    if not isinstance(ext, str) or not (0 < len(ext) <= _MAX_REF):
        return None, "external_ref: порожній/задовгий"

    img = raw.get("image_url")
    if img is not None:
        if not isinstance(img, str) or len(img) > _MAX_URL or urlsplit(img).scheme != "https":
            img = None                                  # погане фото не валить елемент — просто нема

    variant = raw.get("variant_note")
    if variant is not None and (not isinstance(variant, str) or len(variant) > 120):
        variant = None

    in_stock = raw.get("in_stock", True)
    if not isinstance(in_stock, bool):
        in_stock = True

    promo = raw.get("promo_until")   # ISO-дата кінця дії ціни; формат перевіряємо, зміст — ні
    if not (isinstance(promo, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", promo)):
        promo = None

    return RawItem(
        external_ref=canon_ref(ext),
        url=url,
        title=title.strip(),
        price_now_kop=now,
        price_old_kop=old,
        in_stock=in_stock,
        image_url=img,
        variant_note=variant,
        promo_until=promo,
    ), None


def ingest_batch(conn, source: str, items: list, category_slug: str | None = None) -> dict:
    """Валідує й персистить батч від колектора. Погані елементи ВІДКИДАЄ (не валить добрі).

    `scan_run` — песимістично 'failed'→'ok' (T13). `source_method='satellite'` фіксує
    провенанс: ці снапшоти прийшли не з нашого прямого збору.
    """
    if source not in INGEST_SOURCES:
        raise ValueError(f"невідоме джерело: {source!r}")
    if not isinstance(items, list):
        raise ValueError("items має бути списком")

    valid: list[RawItem] = []
    seen: set[str] = set()
    rejected: list[str] = []
    for raw in items[:5000]:                            # стеля батчу — проти зловмисного роздування
        if not isinstance(raw, dict):
            rejected.append("не-обʼєкт"); continue
        item, why = validate_item(source, raw)
        if item is None:
            rejected.append(why or "?"); continue
        if item.external_ref in seen:                   # дедуп у межах батчу
            continue
        seen.add(item.external_ref)
        valid.append(item)

    base_url = INGEST_SOURCES[source]["base_url"]
    source_id = upsert_source(conn, source, base_url, adapter_kind="ssr",
                              platform="custom", fetch_tier="A")
    scan_run_id = conn.execute(
        "INSERT INTO scan_run (source_id, surface, status) VALUES (%s,'discovery','failed') "
        "RETURNING scan_run_id", (source_id,)).fetchone()[0]

    categories = load_categories(conn)
    n = persist_items(conn, source_id, valid, categories, source_method="satellite",
                      scan_run_id=scan_run_id, category_slug=category_slug)

    status = "ok" if valid and not rejected else ("partial" if valid else "failed")
    conn.execute("UPDATE scan_run SET finished_at = now(), items_seen = %s, status = %s "
                 "WHERE scan_run_id = %s", (n, status, scan_run_id))

    # унікальні причини відмов (без спаму) — щоб колектор бачив, що відкинуто й чому
    reasons: dict[str, int] = {}
    for r in rejected:
        reasons[r] = reasons.get(r, 0) + 1
    return {"source": source, "accepted": n, "rejected": len(rejected),
            "reasons": reasons, "status": status}


# ── html-ingest: застосунок шле сирий HTML, СЕРВЕР парсить (S11 етап 3) ────────────
def collect_plan() -> list[dict]:
    """Що застосунку-колектору тягнути. Сервер — авторитет (додати крамницю = зміна ТУТ,
    не оновлення застосунку). Для hub-джерел віддаємо хаб; сервер сам зробить discover()
    з присланого HTML і поверне лендинги наступним кроком."""
    out: list[dict] = []
    for name, cfg in HTML_SOURCES.items():
        mode = cfg.get("mode", "fetch")
        if cfg.get("hub"):
            out.append({"source": name, "url": cfg["hub"], "kind": "hub", "mode": mode})
        for u, _ in source_listings(cfg):               # лістинги + їхня пагінація
            out.append({"source": name, "url": u, "kind": "page", "mode": mode})
    return out


def ingest_html(conn, source: str, url: str, html: str) -> dict:
    """Сирий HTML від колектора → СЕРВЕР парсить адаптером → та сама валідація+персист,
    що й /api/ingest (довіра до людини ≠ довіра до кожного байта — усе перевіряється).

    Двофазно для hub-джерел: якщо `url` — хаб, повертаємо discover()-лендинги (accepted=0);
    застосунок дотягне їх наступними викликами (kind='page'). Так уся логіка парсингу
    лишається на сервері — застосунок лише fetch+forward.
    """
    if source not in HTML_SOURCES:
        raise ValueError(f"невідоме html-джерело: {source!r}")
    if source not in INGEST_SOURCES:
        raise ValueError(f"джерело {source!r} без host-політики")
    hosts = INGEST_SOURCES[source]["hosts"]

    if not isinstance(url, str) or not (0 < len(url) <= _MAX_URL):
        raise ValueError("url: порожній/задовгий")
    if urlsplit(url).scheme != "https":
        raise ValueError("url: лише https")
    if not _host_ok(url, hosts):
        raise ValueError(f"url не на домені {source} ({hosts})")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("html: порожній")
    if len(html) > _MAX_HTML:
        raise ValueError(f"html: завеликий (>{_MAX_HTML} байт)")

    cfg = HTML_SOURCES[source]
    adapter = cfg["adapter"]

    # фаза 1: хаб → лендинги (discover робить СЕРВЕР, не застосунок)
    if cfg.get("hub") and canon_ref(url) == canon_ref(cfg["hub"]):
        try:
            landings = adapter.discover(html)[: cfg.get("max_pages", 20)]
        except Exception as e:
            raise ValueError(f"discover: {type(e).__name__}: {e}")
        # лендинги мусять лишатись на домені джерела (не дати збити застосунок на чужий хост)
        landings = [u for u in landings if _host_ok(u, hosts)]
        return {"source": source, "kind": "hub", "discovered": landings,
                "accepted": 0, "rejected": 0, "status": "ok"}

    # фаза 2: сторінка → екстракт → та сама валідація+персист, що й прямий /api/ingest
    try:
        extracted = adapter.extract(html)
    except Exception as e:
        raise ValueError(f"extract: {type(e).__name__}: {e}")
    items = [dataclasses.asdict(it) for it in extracted]
    # категорія — з ЛІСТИНГА, який зібрали (надійно): спершу поіменний тег URL, тоді
    # джерело-рівневий дефолт (hub); нема — persist_items вгадає з URL (categorize).
    category_slug = URL_CATEGORY.get((source, url)) or cfg.get("category")
    result = ingest_batch(conn, source, items, category_slug=category_slug)
    result["kind"] = "page"
    return result
