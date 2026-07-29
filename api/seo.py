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


def sitemap(categories, product_ids, stores=(), models=(), sections=()) -> str:
    """Карта сайту. Стрічку каталогу малює JS, тож сторінки товарів мусять бути тут —
    інакше до них немає жодного шляху, яким пройде краулер."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           _url(SITE + "/", "hourly", "1.0"),
           _url(SITE + "/catalog", "hourly", "0.9")]
    # Розділи — ВИЩЕ за категорії: 31 сторінка, кожна веде у свої категорії. Доти
    # карта сайту знала 159 категорій і 0 розділів, тобто рівень над категорією
    # краулер бачити не міг узагалі.
    for slug in sections:
        out.append(_url(f"{SITE}/section/{slug}", "daily", "0.8"))
    for slug in categories:
        out.append(_url(f"{SITE}/catalog?c={slug}", "daily", "0.7"))
    for pid in product_ids:
        out.append(_url(f"{SITE}/product/{pid}", "daily", "0.6"))
    out.append(_url(SITE + "/drops", "hourly", "0.9"))      # єдине, чого нема ні в кого
    out.append(_url(SITE + "/how", "monthly", "0.8"))       # метод — обличчя продукту
    out.append(_url(SITE + "/verify", "daily", "0.8"))      # доказ, якого нема ні в кого
    out.append(_url(SITE + "/stores", "weekly", "0.6"))
    for slug in stores:
        out.append(_url(f"{SITE}/store/{slug}", "daily", "0.5"))
    # Моделі — лише ті, що є в 2+ крамницях: сторінка з однією пропозицією не додає
    # нічого понад сторінку товару, тобто була б дублем у видачі.
    for pid in models:
        out.append(_url(f"{SITE}/model/{pid}", "daily", "0.7"))
    out.append(_url(SITE + "/catalog?b=verified", "hourly", "0.8"))
    out.append(_url(SITE + "/catalog?b=pumped", "hourly", "0.8"))
    for p in ("privacy", "terms", "support", "delete-account"):
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


# ─────────────────────────── обличчя сторінок каталогу (S27) ───────────────────
BADGE_PAGE = {
    "verified": ("Перевірені знижки — {b}",
                 "Знижки, де ціна справді нижча за все, що ми бачили за 30 днів."),
    "pumped":   ("Знижки із завищеною «старою» ціною — {b}",
                 "Товари, де «стара» ціна вища за фактичний мінімум наших спостережень "
                 "за 30 днів."),
    # `sale` — не стан бейджа, а зріз каталогу (S34): «усе, що зараз зі знижкою».
    "sale":     ("Знижки в українських крамницях — {b}",
                 "Товари, на які зараз заявлено знижку. Кожну звіряємо з власною "
                 "історією цін за 30 днів."),
}


def catalog_head(*, category=None, section=None, badge=None, query=None) -> str:
    """<head> каталогу З УРАХУВАННЯМ фільтра.

    ⚠ До 2026-07-27 усі 148 адрес `?c=…` віддавали однаковий заголовок і canonical на
    `/catalog` — тобто sitemap перелічував сторінки, які САМІ казали краулеру «я копія,
    індексуй іншу». Тепер у кожної свій титул, свій опис і canonical на себе.

    Пошук (`?q=`) навмисно `noindex`: сторінка результатів — не контент, а відповідь на
    чужий запит; індексувати такі — класичний спосіб засмітити видачу власним сайтом."""
    path, title, desc, noindex = "/catalog", None, None, False
    if query:
        return "\n".join(_tags(f"Пошук: {query} — {BRAND}",
                               "Результати пошуку за назвою товару.",
                               f"{SITE}/catalog", noindex=True))
    if category:
        n = category.get("n") or 0
        path = f"/catalog?c={category['slug']}"
        # ⚠ З S34 сторінка категорії показує ВСІ товари, не лише знижкові: у базі
        # 59 445 товарів, знижку має 28 504. Титул, який обіцяє самі знижки, обіцяв
        # би половину того, що на сторінці насправді.
        title = f"{category['name']} — ціни та знижки в українських крамницях | {BRAND}"
        desc = (f"Ціни на {n} товарів у категорії «{category['name']}». Кожну заявлену "
                f"знижку звіряємо з власною історією цін за 30 днів."
                if n else
                f"Категорія «{category['name']}»: стежимо за цінами й звіряємо знижки з "
                f"власною історією спостережень.")
    elif section:
        path = f"/catalog?s={section}"
        title = f"{section} — ціни та знижки | {BRAND}"
        desc = (f"Товари розділу «{section}»: ціни з українських крамниць, знижки "
                f"звірені з нашою історією спостережень за 30 днів.")
    elif badge in BADGE_PAGE:
        t, d = BADGE_PAGE[badge]
        path = f"/catalog?b={badge}"
        title, desc = t.format(b=BRAND), d
    else:
        title = f"Каталог цін українських крамниць — {BRAND}"
        desc = ("Ціни на 59 тисяч товарів із українських онлайн-крамниць. Кожну заявлену "
                "знижку звіряємо з власною історією цін за 30 днів.")
    return "\n".join(_tags(title, desc, SITE + path, noindex=noindex))


def section_head(name: str, slug: str, n_cats: int, n_items: int) -> str:
    """<head> сторінки розділу (S34). Проміжний рівень між головною і 173 категоріями:
    доти він існував лише як фільтр `?s=`, тобто адреси не мав узагалі."""
    title = f"{name} — ціни та знижки | {BRAND}"
    desc = (f"{n_items} товарів у {n_cats} категоріях розділу «{name}». Ціни з "
            f"українських крамниць; заявлені знижки звіряємо з власною історією за 30 днів."
            if n_items else
            f"Розділ «{name}»: стежимо за цінами українських крамниць.")
    return "\n".join(_tags(title, desc, f"{SITE}/section/{slug}"))


def store_head(store: dict) -> str:
    n, v = store.get("discounts") or 0, store.get("verified") or 0
    title = f"{store['name']} — знижки та історія цін | {BRAND}"
    desc = (f"Стежимо за цінами {store['name']}: {n} активних знижок, з них {v} пройшли "
            f"перевірку 30-денним мінімумом. Лише факти наших спостережень.")
    return "\n".join(_tags(title, desc, f"{SITE}/store/{store['slug']}"))


def model_head(m: dict) -> str:
    """<head> сторінки моделі. Опис — з ФАКТІВ: діапазон цін і скільки крамниць."""
    n = m.get("stores_n") or 0
    lo, hi = m.get("min_kop"), m.get("max_kop")
    title = f"{m.get('title') or 'Модель'} — ціни в {n} крамницях | {BRAND}"
    if lo is not None and hi is not None and hi > lo:
        desc = (f"Від {grn(lo)} до {grn(hi)} у {n} крамницях. Ціни й історію звіряємо "
                f"з власними спостереженнями.")
    elif lo is not None:
        desc = f"{grn(lo)}. Ціни й історію звіряємо з власними спостереженнями."
    else:
        desc = "Порівняння цін на цю модель за нашими спостереженнями."
    return "\n".join(_tags(title, desc, f"{SITE}/model/{m['product_id']}", kind="product"))


def model_summary(m: dict) -> str:
    """Розмітка для того, хто не виконує JS: назва, діапазон, перелік крамниць."""
    parts = [f"<h1>{html.escape(m.get('title') or '')}</h1>"]
    lo = m.get("min_kop")
    if lo is not None:
        parts.append(f'<p class="pbuy"><span class="now">від {grn(lo)}</span></p>')
    for o in (m.get("offers") or [])[:8]:
        price = grn(o["current_kop"]) if o.get("current_kop") is not None else "—"
        parts.append(f'<p>{html.escape(str(o.get("store") or ""))}: {price} — '
                     f'<a href="/product/{o["store_product_id"]}">історія ціни</a></p>')
    return "\n".join(parts)
