"""Адаптер Rozetka (rozetka.com.ua) — лістинги категорій. Тир A: SSR plain-GET.

Розвідка 2026-07-19 (резидентний IP; з ДЦ 403 → джерело сателітне): найбільший
маркетплейс UA, Angular-SSR рендерить 60 карток зі структурою:

    <rz-catalog-tile>
      <a class="tile-title" href="https://rozetka.com.ua/ua/samsung-sm-s948bzvgeuc/p570541936/">
        Мобільний телефон Samsung Galaxy S26 Ultra 12/512GB Cobalt Violet (SM-S948BZVGEUC)</a>
      <div class="price">65 299₴</div>
      <div class="old-price">70 999₴</div>       ← лише у знижкових (38/60)
      <img src="https://content2.rozetka.com.ua/...">

MPN і в назві (дужки), і в URL-слагі → матчинг T15. Стабільний ключ — /pNNN/ product-id.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

# JSON-LD Offer: сама Rozetka декларує кінець дії ціни (schema.org priceValidUntil).
# Мапимо url товару → дата. url стоїть перед offers у тому ж product-обʼєкті.
_PVU = re.compile(
    r'"url":"(https://rozetka\.com\.ua/[^"]+?/p\d+/)"'
    r'.{0,400}?"offers":\{[^}]*?"priceValidUntil":"(\d{4}-\d{2}-\d{2})"'
)


class RozetkaAdapter:
    source_name = "Rozetka"

    def _promo_map(self, html: str) -> dict[str, str]:
        """{шлях_url: priceValidUntil} з JSON-LD (де крамниця дала реальну дату)."""
        out: dict[str, str] = {}
        for url, date in _PVU.findall(html):
            out[canon_ref(urlsplit(url).path)] = date
        return out

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        promo = self._promo_map(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css("rz-catalog-tile"):
            a = card.css_first("a.tile-title")
            title = a.text(strip=True) if a else ""
            url = (a.attributes.get("href") or "").split("?")[0].split("#")[0] if a else ""
            if not title or "rozetka.com.ua" not in url:
                continue

            cur_node = card.css_first(".price")
            now_kop = parse_price_to_kop(cur_node.text() if cur_node else None)
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна

            old_node = card.css_first(".old-price")
            old_kop = parse_price_to_kop(old_node.text() if old_node else None)
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            img = card.css_first("img")
            image_url = (img.attributes.get("src") or img.attributes.get("data-src")) if img else None
            if image_url and not image_url.startswith("https://"):
                image_url = None

            ext = canon_ref(urlsplit(url).path)   # /ua/<slug>/pNNN — стабільний product-id (§4.8)
            if ext in seen:                       # дедуп у межах сторінки (§10.1)
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
                in_stock=True,                # лістинг не маркує відсутність; OOS зникає з видачі
                image_url=image_url,
                discount_pct=pct,
                promo_until=promo.get(ext),   # дата кінця дії ціни (якщо крамниця дала)
            ))
        return items
