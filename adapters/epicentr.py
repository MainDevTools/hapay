"""Адаптер Епіцентру (epicentrk.ua) — лістинг категорії. Тир A: SSR plain-GET.

Розвідка 2026-07-21. Найкращий випадок із усіх дев'яти крамниць: сторінка віддає
товари РОЗМІТКОЮ schema.org, тож екстракція йде першим тиром порядку (§8.4,
structured-data-first) — не CSS-селекторами по класах, які крамниця може перейменувати
будь-якого дня. Класи в Епіцентрі до того ж хешовані Nuxt-ом (`_Al-5uY1o`), тобто
чіплятись за них було б свідомо крихко.

Кожна картка — `itemscope itemtype=https://schema.org/Product` з itemprop:
name / url / image / offers(price, priceCurrency, availability).

    <div itemscope itemtype="https://schema.org/Product" itemprop="item">
      <a href="/ua/shop/noutbuk-acer-…html" itemprop="url"><img itemprop="image" …></a>
      <p itemprop="name">Ноутбук Acer Aspire Lite AL15-41P-R4L1 15,6" (NX.J98EU.004)</p>
      <div itemscope itemtype="https://schema.org/Offer" itemprop="offers">
        <meta itemprop="availability" content="http://schema.org/InStock">
        <div data-product-price-main><data itemprop="price" content="25999.00">25 999</data></div>
        <s data-product-price-old><data itemprop="price" content="72777.00">72 777</data></s>

⚠ ПАСТКА, на яку легко наступити: перекреслена СТАРА ціна має той самий
`itemprop="price"`, що й поточна. Селектор `[itemprop=price]` без розрізнення за
`data-product-price-main` / `-old` брав би стару ціну як поточну — тихо, без помилки,
і ми б рахували знижки від неправильного числа. Тому читаємо ЛИШЕ через ці атрибути.

Пагінація — `?PAGEN_1=N` (Bitrix). Це теж перевірено фактом, бо звичні схеми брешуть:
`?page=2` і `?p=2` віддають 200 і рівно ті самі 60 товарів (перетин зі стор.1 = 60),
тобто мовчки дублювали б першу сторінку — та сама пастка, що вже була з Allo.
`?PAGEN_1=2/3/5` → по 60 позицій, перетин з першою нульовий.

MPN у назві в дужках → матчинг T15, як у решти крамниць.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://epicentrk.ua"


def _price(card, attr: str) -> int | None:
    """Ціна з зони `data-product-price-main` / `-old`.

    Беремо `content` (машинне «25999.00»), а не текст: текст містить нерозривні
    пробіли й «₴/шт.», і його довелось би чистити. `content` — те саме число, але
    вже придатне до розбору.
    """
    zone = card.css_first(f"[{attr}]")
    if zone is None:
        return None
    node = zone.css_first('[itemprop="price"]') or zone
    return parse_price_to_kop(node.attributes.get("content") or node.text())


class EpicentrAdapter:
    source_name = "Epicentr"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css('[itemtype$="schema.org/Product"]'):
            name = card.css_first('[itemprop="name"]')
            title = name.text(strip=True) if name else ""
            if not title:
                continue

            a = card.css_first('a[itemprop="url"]') or card.css_first('a[href*="/shop/"]')
            href = (a.attributes.get("href") or "").split("?")[0].split("#")[0] if a else ""
            if not href:
                continue
            url = href if href.startswith("http") else BASE + href

            now_kop = _price(card, "data-product-price-main")
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна
            old_kop = _price(card, "data-product-price-old")
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            avail = card.css_first('[itemprop="availability"]')
            in_stock = "OutOfStock" not in (avail.attributes.get("content") or "") if avail else True

            img = card.css_first('img[itemprop="image"]')
            image_url = img.attributes.get("src") if img else None

            ext = canon_ref(urlsplit(url).path)   # /ua/shop/<slug>.html — стабільний ключ (§4.8)
            if ext in seen:                       # дедуп у межах сторінки (§10.1)
                continue
            seen.add(ext)

            items.append(RawItem(
                external_ref=ext,
                url=url,
                title=title,
                price_now_kop=now_kop,
                price_old_kop=old_kop,
                in_stock=in_stock,
                image_url=image_url,
            ))
        return items
