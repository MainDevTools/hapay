"""Адаптер Moyo (moyo.ua) — лістинги категорій. Тир A: чистий plain-GET.

Розвідка 2026-07-19 (резидентний IP; з ДЦ Hetzner — 403, тому джерело сателітне):
лістинг SSR-ить картки, ціни текстом, фото — base64-вказівник (lazy-load):

    <div class="product-card">
      <a href="https://www.moyo.ua/ua/smartfon_….html">…
        <div class="product-card_title_tooltip">Смартфон Apple iPhone 17 … (MFYM4AF/A)</div>
      <img class="first-image lazy-intersection" data-srcset-hash="aHR0cHM6…">   ← base64(URL фото)
      <div class="product-card_price_oldprice"> 72 999₴ </div>
      <div class="product-card_price_current sale"> 66 999₴ </div>

MPN у назві (дужки наприкінці) → матчинг T15 працює з коробки.
Фото: декодуємо base64 → https://i.moyo.ua/… — це ВКАЗІВНИК (hotlink), не байти (§7.4).
"""
from __future__ import annotations

import base64
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop


def _unb64_url(s: str | None) -> str | None:
    """data-srcset-hash → https-URL фото або None (сміття не валить картку)."""
    if not s:
        return None
    try:
        url = base64.b64decode(s, validate=True).decode("utf-8", "strict")
    except Exception:
        return None
    return url if url.startswith("https://") else None


class MoyoAdapter:
    source_name = "Moyo"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css("div.product-card"):
            a = card.css_first('a[href*="moyo.ua/"]')
            url = (a.attributes.get("href") or "").split("?")[0].split("#")[0] if a else ""
            if not url.endswith(".html"):
                continue

            title_node = card.css_first(".product-card_title_tooltip")
            title = title_node.text(strip=True) if title_node else ""
            if not title:
                continue

            cur_node = card.css_first(".product-card_price_current")
            now_kop = parse_price_to_kop(cur_node.text() if cur_node else None)
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна

            old_node = card.css_first(".product-card_price_oldprice")
            old_kop = parse_price_to_kop(old_node.text() if old_node else None)
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            img = card.css_first("img.first-image")
            image_url = _unb64_url(img.attributes.get("data-srcset-hash")) if img else None

            ext = canon_ref(urlsplit(url).path)   # шлях без хоста → стабільний ключ (§4.8)
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
            ))
        return items
