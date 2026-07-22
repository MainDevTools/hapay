"""Адаптер Аптеки Доброго Дня (add.ua) — ДВОФАЗНИЙ: лістинг → сторінки товарів.

Чому двофазний, коли Подорожник — ні. Штрихкод (наш ключ матчингу за GTIN) add.ua
віддає ЛИШЕ на сторінці товару, не в лістингу. Тож збираємо як хаб Allo: лістинг
категорії `discover()`-ить URL товарів → кожен телефон дотягує окремо → `extract()`
парсить штрихкод. Це дорого (рендер кожної картки), тому свідомо ЛИШЕ дермокосметика —
єдиний розділ, де асортимент перетинається з Подорожником (спільні La Roche-Posay та
ін.; заміряно 2026-07-22, решта категорій дали нуль перетину). Cloudflare → mode=render.

    discover(лістинг)      → ItemList ld+json → URL товарів (.html).
    extract(сторінка_товару) → один товар:
        назва/ціна/наявність — ld+json Product (offers.price надійна);
        штрихкод — рядок таблиці «Штрих-код»: <td data-th="Штрих-код">4820274801259</td>;
        власний URL — <link rel=canonical> (адаптер отримує лише HTML, не URL).

⚠ ld+json тут має `gtin13` = ВНУТРІШНІЙ SKU (напр. "822072"), НЕ штрихкод — не брати
його. Справжній EAN лише в рядку «Штрих-код». (Тому й per-товар: у лістингу його нема.)
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref

BASE = "https://www.add.ua"


def _ld(tree) -> list[dict]:
    out = []
    for s in tree.css('script[type="application/ld+json"]'):
        try:
            d = json.loads(s.text())
        except (ValueError, TypeError):
            continue
        out += (d if isinstance(d, list) else [d])
    return [o for o in out if isinstance(o, dict)]


def _kop(v) -> int | None:
    if v is None:
        return None
    try:
        n = float(str(v).replace(",", ".").replace(" ", ""))
    except ValueError:
        return None
    return int(round(n * 100)) if n > 0 else None


class AdduaAdapter:
    source_name = "AddUa"

    def discover(self, html: str) -> list[str]:
        """URL товарів із лістинга (ItemList ld+json). Порядок збережено, дедуп."""
        urls, seen = [], set()
        for o in _ld(LexborHTMLParser(html)):
            if o.get("@type") != "ItemList":
                continue
            for e in o.get("itemListElement", []) or []:
                u = e.get("url") or (e.get("item") or {}).get("url")
                if not u or not u.endswith(".html"):
                    continue
                u = u if u.startswith("http") else BASE + u
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
        offers = prod.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        offers = offers or {}
        now_kop = _kop(offers.get("price"))
        if not title or now_kop is None:
            return []                          # без назви/ціни — не товар

        in_stock = "OutOfStock" not in str(offers.get("availability") or "")

        # штрихкод — рядок таблиці «Штрих-код». НЕ ld+json gtin13 (там внутрішній SKU).
        gtins: tuple[str, ...] = ()
        for td in tree.css("td[data-th]"):
            if "трих" in (td.attributes.get("data-th") or ""):   # Штрих-код / штрих-код
                code = re.sub(r"\D", "", td.text())
                if code:
                    gtins = (code,)
                break

        can = tree.css_first('link[rel="canonical"]')
        url = (can.attributes.get("href") if can else None)
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
            external_ref=canon_ref(urlsplit(url).path),   # /ua/<slug>.html
            url=url,
            title=title,
            price_now_kop=now_kop,
            price_old_kop=None,               # дермокосметика: старої ціни в ld+json нема
            in_stock=in_stock,
            image_url=image_url,
            gtins=gtins,
        )]
