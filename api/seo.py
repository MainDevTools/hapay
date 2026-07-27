"""Те, що бачать МАШИНИ: прев'ю посилань, structured data, sitemap, robots.

Навіщо взагалі. Сайт малюється клієнтом, тож усе, що не виконує JS, бачить порожню
оболонку. Це стосується не лише пошуковиків: **прев'ю посилання в Telegram, Viber,
Facebook** будує бот, який JS не виконує зовсім. До 2026-07-27 посилання на товар
розкривалось у чаті голим URL — без назви, ціни й натяку, що там історія цін. Для
продукту, чия головна поверхня — Telegram, це найдорожча дірка з дешевих.

Тому теги збираємо НА СЕРВЕРІ й підставляємо в готовий HTML. Шаблонізатора не
заводимо: одна заміна маркера `<!--SEO-->` дешевша за нову залежність.

⚠ Межі, продиктовані інваріантом B (юридика — найтвердіше):

* **Опису товару нема й не буде.** Ми не зберігаємо зв'язний текст крамниць — ані
  байта. `og:description` збираємо САМІ з фактів (назва, ціна, крамниця) плюс власне
  твердження про перевірку. Те саме в JSON-LD: поля `description` там немає навмисно.
* **Фото товару не йде в прев'ю.** Соцмережа не просто показує `og:image` — вона його
  ЗАВАНТАЖУЄ й кешує в себе. Тир «hotlink» цього не покриває: hotlink — коли байти
  бере браузер читача. Тому в прев'ю власна брендова картка `/s/og.png`. Чи можна
  колись фото товару — питання юридичне, тобто 🧭 оператора, не наше.
"""
from __future__ import annotations

import html
import json
import time

SITE = "https://hapay.today"
BRAND = "Хапай"
TAGLINE = "знижки, перевірені історією цін"


def _e(s) -> str:
    """Екранування для АТРИБУТА: лапки обов'язково, інакше назва з `"` рве розмітку."""
    return html.escape(str(s or ""), quote=True)


def grn(kop) -> str:
    """Копійки → «19 999 ₴». Цілі гривні без «,00» — як у застосунку (Money.Grn)."""
    if kop is None:
        return ""
    whole, rest = divmod(int(kop), 100)
    body = f"{whole:,}".replace(",", " ")
    return f"{body},{rest:02d} ₴" if rest else f"{body} ₴"


BADGE_LINE = {
    "verified": "Знижка перевірена нашою історією цін.",
    "verified_provisional": "Знижка перевірена нашою історією цін.",
    "pumped": "«Стара» ціна вища за все, що ми бачили за 30 днів.",
}


def product_description(card: dict) -> str:
    """Опис прев'ю — з ФАКТІВ, не з тексту крамниці (інваріант B).

    Порядок: ціна → крамниця → що ми про знижку знаємо. Перші ~120 символів — усе,
    що покаже Telegram, тож головне попереду."""
    bits = []
    if card.get("current_kop") is not None:
        p = grn(card["current_kop"])
        old = card.get("old_declared_kop")
        bits.append(f"{p} замість {grn(old)}" if old and old > card["current_kop"] else p)
    if card.get("store"):
        bits.append(str(card["store"]))
    head = " · ".join(bits)
    tail = BADGE_LINE.get(card.get("badge_state") or "")
    if not tail:
        ref = card.get("reference_kop")
        tail = (f"За нашими спостереженнями ціна за 30 днів не була нижчою за {grn(ref)}."
                if ref is not None else
                "Показуємо власну історію спостережень за ціною.")
    return f"{head} — {tail}" if head else tail


def product_jsonld(card: dict) -> str:
    """Schema.org Product+Offer. Лише факти, які ми й так публікуємо на сторінці.

    `description` НЕМАЄ навмисно (див. модуль). `image` немає з тієї ж причини, що й
    у og:image. `priceValidUntil` не ставимо: ми не знаємо, доки крамниця тримає ціну,
    а вигадана дата — це твердження, якого ми не міряли."""
    offer = {
        "@type": "Offer",
        "url": f"{SITE}/product/{card['store_product_id']}",
        "priceCurrency": "UAH",
        "availability": "https://schema.org/InStock",
    }
    if card.get("current_kop") is not None:
        offer["price"] = f"{int(card['current_kop']) / 100:.2f}"
    if card.get("store"):
        offer["seller"] = {"@type": "Organization", "name": card["store"]}
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": card.get("title") or "",
        "url": offer["url"],
        "offers": offer,
    }
    if card.get("category"):
        data["category"] = card["category"]
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _tags(title: str, desc: str, url: str, *, kind: str = "website",
          noindex: bool = False) -> list[str]:
    t = [
        f'<title>{_e(title)}</title>',
        f'<meta name="description" content="{_e(desc)}">',
        f'<link rel="canonical" href="{_e(url)}">',
        f'<meta property="og:type" content="{kind}">',
        f'<meta property="og:site_name" content="{BRAND}">',
        f'<meta property="og:locale" content="uk_UA">',
        f'<meta property="og:title" content="{_e(title)}">',
        f'<meta property="og:description" content="{_e(desc)}">',
        f'<meta property="og:url" content="{_e(url)}">',
        f'<meta property="og:image" content="{SITE}/s/og.png">',
        f'<meta property="og:image:width" content="1200">',
        f'<meta property="og:image:height" content="630">',
        f'<meta name="twitter:card" content="summary_large_image">',
        # іконки — тут, а не в кожній сторінці: одне місце, жодного розсинхрону
        f'<link rel="icon" href="/favicon.ico" sizes="any">',
        f'<link rel="icon" type="image/png" sizes="32x32" href="/s/icon-32.png">',
        f'<link rel="apple-touch-icon" href="/s/icon-180.png">',
        f'<meta name="theme-color" content="#1a813c">',
    ]
    if noindex:
        t.append('<meta name="robots" content="noindex">')
    return t


def product_head(card: dict) -> str:
    """Блок у <head> сторінки товару: прев'ю + structured data."""
    title = f"{card.get('title') or 'Товар'} — ціна та історія | {BRAND}"
    desc = product_description(card)
    url = f"{SITE}/product/{card['store_product_id']}"
    tags = _tags(title, desc, url, kind="product")
    tags.append(f'<script type="application/ld+json">{product_jsonld(card)}</script>')
    return "\n".join(tags)


def product_summary(card: dict) -> str:
    """Мінімальна РОЗМІТКА товару для того, хто не виконує JS.

    Той самий контейнер потім перемальовує скрипт сторінки, тож дублювання на екрані
    не буде: це не «версія без JS», а те, з чим сторінка приїжджає. Заголовок і ціна
    в HTML означають, що сторінка не порожня навіть до першого запиту до API."""
    parts = [f"<h1>{html.escape(card.get('title') or '')}</h1>"]
    if card.get("current_kop") is not None:
        parts.append(f'<p class="pbuy"><span class="now">{grn(card["current_kop"])}</span></p>')
    if card.get("store"):
        parts.append(f'<p class="meta"><b>{html.escape(str(card["store"]))}</b></p>')
    if card.get("url"):
        parts.append(f'<p><a href="{_e(card["url"])}" rel="nofollow noopener">Відкрити в крамниці</a></p>')
    return "\n".join(parts)


def page_head(title: str, desc: str, path: str, *, noindex: bool = False) -> str:
    """Для сторінок без даних із БД (головна, каталог, вхід, юр-сторінки)."""
    return "\n".join(_tags(title, desc, SITE + path, noindex=noindex))


# ⚠ /s/ НЕ закривати: там лежать стилі, скрипти й сама картинка прев'ю. Краулер, який
# не може взяти CSS/JS, бачить зламану сторінку й судить по ній; бот соцмережі без
# доступу до og.png покаже картку без зображення. Закриваємо лише службове й приватне.
ROBOTS = f"""User-agent: *
Disallow: /api/
Disallow: /admin
Disallow: /login
Disallow: /me

Sitemap: {SITE}/sitemap.xml
"""


def _url(loc: str, changefreq: str, priority: str) -> str:
    return (f"<url><loc>{_e(loc)}</loc><changefreq>{changefreq}</changefreq>"
            f"<priority>{priority}</priority></url>")


def sitemap(categories, product_ids) -> str:
    """Карта сайту. Стрічку каталогу малює JS, тож сторінки товарів мусять бути тут —
    інакше до них немає жодного шляху, яким пройде краулер."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           _url(SITE + "/", "hourly", "1.0"),
           _url(SITE + "/catalog", "hourly", "0.9")]
    for slug in categories:
        out.append(_url(f"{SITE}/catalog?c={slug}", "daily", "0.7"))
    for pid in product_ids:
        out.append(_url(f"{SITE}/product/{pid}", "daily", "0.6"))
    for p in ("privacy", "terms", "support"):
        out.append(_url(f"{SITE}/{p}", "monthly", "0.2"))
    out.append("</urlset>")
    return "\n".join(out)


class Cached:
    """Sitemap на десятки тисяч рядків не варто збирати на кожен запит краулера."""

    def __init__(self, ttl_s: int):
        self.ttl = ttl_s
        self._value = None
        self._at = 0.0

    def get(self, build):
        now = time.monotonic()
        if self._value is None or now - self._at > self.ttl:
            self._value = build()
            self._at = now
        return self._value
