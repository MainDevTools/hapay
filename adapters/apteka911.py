"""Адаптер Аптеки 911 (apteka911.ua) — ДВОФАЗНИЙ: лістинг → сторінки товарів.
Третя аптека (розвідка 2026-07-22). Тир: SSR-HTML, plain-GET (mode=fetch — БЕЗ рендера,
на відміну від add.ua; сайт віддає повний HTML з резидентного IP без Cloudflare-виклику).

ЧОМУ ДВОФАЗНИЙ. Наш ключ матчингу — штрихкод — apteka911 кладе ЛИШЕ на сторінку товару, і
то в дивному місці: у `<title>` в дужках, напр. «…Толеран 40 мл (3337875578486) Ля Рош…».
У лістингу штрихкодів нема (заміряно: 0 EAN на 101 картку). Тож як add.ua/Allo: лістинг
`discover()`-ить URL товарів → кожен телефон дотягує окремо → `extract()` бере штрихкод.

    discover(лістинг)        → <a href> з патерном `/ua/shop/<slug>-p<id>` (дедуп).
    extract(сторінка_товару) → один товар:
        назва/фото/наявність — ld+json Product (заміряно: name/image/availability 25/25);
        ЦІНА — DOM `.price-new` (в ld+json Offer.price = None — не брати звідти!);
        ШТРИХКОД — `<title>` у дужках (єдине надійне джерело; у характеристиках нема);
        власний URL — <link rel=canonical> (адаптер отримує лише HTML, не URL).

⚠ ld+json тут БЕЗ ціни (Offer.price=None) і БЕЗ gtin13 — беремо звідти тільки name/image/
наявність. Ціна — з видимого DOM, штрихкод — з title. (Тому й per-товар.)

Seed — бренд La Roche-Posay (`/ua/shop/brands/la-roche`, 56 товарів): заміряно 2026-07-22,
~47% штрихкодів уже є в каталозі (Podorozhnyk+AddUa) → миттєві крос-аптечні трійки. Vichy/
інші дерма-бренди на apteka911 великі, але в нашому каталозі їх нема (0 перетину) — цілимо
туди, де вже лежить пара, як робив add.ua з La Roche.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://apteka911.ua"
_PROD_HREF = re.compile(r"/ua/shop/[a-z0-9\-]+-p\d+")   # /ua/shop/<slug>-p<id>
_BARCODE = re.compile(r"\((\d{8,14})\)")                # штрихкод у дужках у <title>


def _ld(tree) -> list[dict]:
    """ld+json блоки сторінки. `strict=False` НАВМИСНО: apteka911 кладе в опис товару
    сирі контрольні символи (перенос рядка) — строгий json.loads на них падає, і Product-
    блок губився б цілком (заміряно 2026-07-22 на картках La Roche). strict=False дозволяє
    контрольні символи всередині рядків — блок парситься, товар не втрачаємо."""
    out: list[dict] = []
    for s in tree.css('script[type="application/ld+json"]'):
        try:
            d = json.loads(s.text(), strict=False)
        except (ValueError, TypeError):
            continue
        out += (d if isinstance(d, list) else [d])
    return [o for o in out if isinstance(o, dict)]


class Apteka911Adapter:
    source_name = "Apteka911"

    def discover(self, html: str) -> list[str]:
        """URL товарів із лістинга (<a href> з патерном `-p<id>`). Порядок збережено, дедуп.
        Один товар має кілька посилань (фото+назва) → дедуп за canon-URL (без -p-дубля)."""
        urls, seen = [], set()
        for m in _PROD_HREF.finditer(html):
            u = BASE + m.group(0)
            if u not in seen:
                seen.add(u)
                urls.append(u)
        return urls

    def extract(self, html: str) -> list[RawItem]:
        """Один товар зі СТОРІНКИ ТОВАРУ (не лістинга)."""
        tree = LexborHTMLParser(html)
        prod = next((o for o in _ld(tree) if "Product" in str(o.get("@type", ""))), None)
        if prod is None:
            return []

        title = (prod.get("name") or "").strip()
        if not title:                                    # ld+json без назви — не товар
            return []

        # ЦІНА — з видимого DOM (.price-new), НЕ з ld+json (там None). Fallback .card-price.
        node = tree.css_first(".price-new") or tree.css_first(".card-price")
        now_kop = parse_price_to_kop(node.text()) if node else None
        if now_kop is None:
            return []                                    # без ціни позиція нам не потрібна

        # стара (заявлена) ціна — .price-old, лише коли ВИЩА за поточну (акція). Заміряно
        # 2026-07-22: серед 30 дерма-товарів знижених не було, тож клас не підтверджено на
        # живому — читаємо захисно (нема/не вища → None; детектору стара не критична, він
        # рахує reference з накопиченої історії).
        old_node = tree.css_first(".price-old")
        old_kop = parse_price_to_kop(old_node.text()) if old_node else None
        if old_kop is not None and old_kop <= now_kop:
            old_kop = None

        # наявність — ld+json Offer.availability
        offers = prod.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        in_stock = "OutOfStock" not in str((offers or {}).get("availability") or "")

        # штрихкод — з <title> у дужках (єдине надійне джерело; у ld+json/характеристиках нема)
        gtins: tuple[str, ...] = ()
        tnode = tree.css_first("title")
        if tnode:
            mb = _BARCODE.search(tnode.text())
            if mb:
                gtins = (mb.group(1),)

        can = tree.css_first('link[rel="canonical"]')
        url = can.attributes.get("href") if can else None
        if not url:
            u = prod.get("url") or ""
            url = u if u.startswith("http") else (BASE + u if u else None)
        if not url:
            return []

        img = prod.get("image")
        if isinstance(img, list):
            img = img[0] if img else None
        image_url = img if (isinstance(img, str) and img.startswith("http")) else None

        return [RawItem(
            external_ref=canon_ref(urlsplit(url).path),   # /ua/shop/<slug>-p<id>
            url=url,
            title=title,
            price_now_kop=now_kop,
            price_old_kop=old_kop,
            in_stock=in_stock,
            image_url=image_url,
            gtins=gtins,
        )]
