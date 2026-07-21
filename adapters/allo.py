"""Адаптер Allo (allo.ua) — маркетплейс, акційні лендинги. Тир A: чистий plain-GET.

Розвідка 2026-07-18: каталог/пошук Allo — client-side (Nuxt), АЛЕ акційні лендинги
`/ua/events-and-discounts/<slug>-action/` SSR-ять повні товарні картки (~60/лендинг):

    <div class="product-card ...">
      ... <a href="https://allo.ua/ua/products/.../nazva.html">
      <div class="product-card__title...">Назва</div>
      <div class="v-pb__old"><span class="sum">4 999</span><span class="currency">₴</span></div>
      <div class="v-pb__cur discount"><span class="sum">4 444</span>...

Discovery дворівневий: хаб `/ua/events-and-discounts/` → лінки `*-action/` → картки.
"""
from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

HUB = "https://allo.ua/ua/events-and-discounts/"
_ACTION_RE = re.compile(r'href="(https://allo\.ua/ua/events-and-discounts/[a-z0-9\-]+-action/)"')


class AlloAdapter:
    source_name = "Allo"

    # ---- рівень 1: хаб → лендинги акцій ----
    def discover(self, hub_html: str) -> list[str]:
        """Лінки на акційні лендинги з хабу (порядок збережено, без дублів)."""
        seen: set[str] = set()
        out: list[str] = []
        for u in _ACTION_RE.findall(hub_html):
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    # ---- рівень 2: лендинг → товари ----
    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css("div.product-card"):
            # Посилання на товар. Раніше вимагали саме `/ua/products/` — і через це
            # категорія телевізорів давала НУЛЬ: Allo лінкує там товари як
            # `/ua/televizory/<назва>.html` (заміряно 2026-07-21: 280 таких лінків на
            # сторінці, а адаптер брав 0). Усередині product-card будь-яке посилання
            # на `.html` — це і є товар, тож звужувати шлях не треба.
            url = ""
            for a in card.css("a[href]"):
                href = (a.attributes.get("href") or "").split("?")[0]
                if href.endswith(".html") and "/ua/" in href:
                    url = href
                    break
            if not url:
                continue

            title_node = card.css_first(".product-card__title")
            title = title_node.text(strip=True) if title_node else ""
            if not title:
                continue

            cur_node = card.css_first(".v-pb__cur .sum")
            now_kop = parse_price_to_kop(cur_node.text() if cur_node else None)
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна

            old_node = card.css_first(".v-pb__old .sum")
            old_kop = parse_price_to_kop(old_node.text() if old_node else None)
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            img = card.css_first('img[src*="i.allo.ua"]')
            image_url = img.attributes.get("src") if img else None

            # шлях без хоста → стабільний ключ (§4.8); дедуп у межах сторінки
            ext = canon_ref(url.split("allo.ua", 1)[-1])
            if ext in seen:
                continue
            seen.add(ext)

            pct = None
            if old_kop:
                pct = round((1 - now_kop / old_kop) * 100)

            items.append(RawItem(
                external_ref=ext,
                url=url,
                title=title,
                price_now_kop=now_kop,
                price_old_kop=old_kop,
                in_stock=True,                # на лендингах немає маркера відсутності; OOS зникає з видачі
                image_url=image_url,
                discount_pct=pct,
            ))
        return items
