"""Адаптер Foxtrot (foxtrot.com.ua) — лістинги категорій. Тир A: чистий plain-GET.

Розвідка 2026-07-19 (резидентний IP; з ДЦ Hetzner — 403, тому джерело сателітне):
лістинг категорії SSR-ить повні картки, дані здебільшого в data-атрибутах:

    <div class="product-card" data-title="Смартфон SAMSUNG … (SM-S942BZKGEUC)"
         data-variant="InStock" data-price="42299">
      <div class="badges">…<span class="discount-percent">-8 %</span>…</div>
      <div itemscope itemtype="…/ImageObject">
        <meta itemprop="thumbnailUrl" content="https://files.foxtrot.com.ua/….jpg">
      <a class="images" href="/uk/shop/smartfoniy-….html">
      <span class="price--old">45 999 ₴</span> <span class="price--current">42 299 ₴</span>

MPN (SM-…) — прямо в data-title → матчинг T15 працює з коробки.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://www.foxtrot.com.ua"


class FoxtrotAdapter:
    source_name = "Foxtrot"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css("div.product-card"):
            title = (card.attributes.get("data-title") or "").strip()
            if not title:
                continue

            # головний лінк картки (a.images); варіації кольору мають клас option — не вони
            a = card.css_first("a.images") or card.css_first('a[href*="/uk/shop/"]')
            href = (a.attributes.get("href") or "").split("?")[0] if a else ""
            if not href.endswith(".html"):
                continue
            url = href if href.startswith("http") else BASE + href

            cur_node = card.css_first(".price--current")
            now_kop = parse_price_to_kop(cur_node.text() if cur_node else None)
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна

            old_node = card.css_first(".price--old")
            old_kop = parse_price_to_kop(old_node.text() if old_node else None)
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            img = card.css_first('meta[itemprop="thumbnailUrl"]')
            image_url = img.attributes.get("content") if img else None
            if image_url and not image_url.startswith("https://"):
                image_url = None

            ext = canon_ref(href if href.startswith("/") else "/" + href.split(".ua", 1)[-1])
            if ext in seen:                   # дедуп у межах сторінки (§10.1)
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
                in_stock=(card.attributes.get("data-variant") or "InStock") == "InStock",
                image_url=image_url,
                discount_pct=pct,
            ))
        return items
