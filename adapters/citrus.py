"""Адаптер Citrus (ctrs.com.ua) — лістинги категорій. Тир A: Next.js SSR, plain-GET.

Розвідка 2026-07-19 (резидентний IP; з ДЦ 403 → сателітне джерело): лістинг SSR-ить
47 карток. CSS-класи ХЕШОВАНІ (`MainProductCard-module__price___34KIa`) — суфікс
`___hash` міняється між білдами, тому селектори ПРЕФІКСНІ (`[class*="…module__root"]`),
а стара ціна — по стабільному `.old-price`. Фото — Next-проксі `/_next/image?url=…`,
декодуємо в пряму CDN-адресу (вказівник, не байти — §7.4).

    <div class="… MainProductCard-module__root___…">
      <a href="/smartfony/s948b-zkg-black-samsung-12512gb-786715.html">
      <div class="… MainProductCard-module__title___…">Смартфон Samsung … (SM-S948BZKGEUC)</div>
      <div class="… MainProductCard-module__price___…">65 299₴</div>
      <div class="old-price mr8">70 999</div>          ← лише у знижкових (44/47)

MPN у назві (дужки) → матчинг T15.
"""
from __future__ import annotations

from urllib.parse import unquote, urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://www.ctrs.com.ua"


def _image(card) -> str | None:
    img = card.css_first("img")
    if img is None:
        return None
    src = img.attributes.get("src") or img.attributes.get("data-src") or ""
    if "/_next/image" in src and "url=" in src:      # Next-проксі → пряма CDN-адреса
        src = unquote(src.split("url=", 1)[1].split("&")[0])
    return src if src.startswith("https://") else None


class CitrusAdapter:
    source_name = "Citrus"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css('[class*="MainProductCard-module__root"]'):
            a = card.css_first('a[href*=".html"]')
            href = (a.attributes.get("href") or "").split("?")[0].split("#")[0] if a else ""
            if not href.endswith(".html"):
                continue
            url = href if href.startswith("http") else BASE + href

            title_node = card.css_first('[class*="MainProductCard-module__title"]')
            title = title_node.text(strip=True) if title_node else ""
            if not title:
                continue

            cur_node = card.css_first('[class*="MainProductCard-module__price___"]')
            now_kop = parse_price_to_kop(cur_node.text() if cur_node else None)
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна

            old_node = card.css_first(".old-price")
            old_kop = parse_price_to_kop(old_node.text() if old_node else None)
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

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
                image_url=_image(card),
                discount_pct=pct,
            ))
        return items
