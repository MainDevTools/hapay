"""Адаптер Comfy (comfy.ua) — лістинги категорій. Тир A: SSR plain-GET (резидентний IP).

Розвідка 2026-07-19: категорія SSR-ить 50 карток; ціни й MPN — у HTML:

    <div class="product-tile-catalog">
      <a href="https://comfy.ua/smartfon-...-sm-s948bzkgeuc.html">
      <div class="product-tile-title">Смартфон Samsung Galaxy S26 Ultra ... (SM-S948BZKGEUC)</div>
      <div class="product-tile-price__current">65 299₴</div>
      <div class="product-tile-price__old-value">70 999 ₴</div>   ← лише у знижкових
      <img class="nci-sl__slide-img" src="https://scdn.comfy.ua/....">

MPN у назві (дужки) і в URL → матчинг T15 з коробки. З ДЦ Comfy 403 (як усі) —
джерело сателітне, тягне телефон.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop


class ComfyAdapter:
    source_name = "Comfy"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css("div.product-tile-catalog"):
            a = card.css_first('a[href*="comfy.ua/"]') or card.css_first("a[href]")
            url = (a.attributes.get("href") or "").split("?")[0].split("#")[0] if a else ""
            if not url.endswith(".html"):
                continue
            if not url.startswith("http"):
                url = "https://comfy.ua" + url

            title_node = card.css_first(".product-tile-title")
            title = title_node.text(strip=True) if title_node else ""
            if not title:
                continue

            cur_node = card.css_first(".product-tile-price__current")
            now_kop = parse_price_to_kop(cur_node.text() if cur_node else None)
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна

            old_node = card.css_first(".product-tile-price__old-value")
            old_kop = parse_price_to_kop(old_node.text() if old_node else None)
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            img = card.css_first("img")
            image_url = img.attributes.get("src") if img else None
            if image_url and not image_url.startswith("https://"):
                image_url = None

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
