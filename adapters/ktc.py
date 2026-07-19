"""Адаптер KTC (ktc.ua) — лістинг смартфонів. Тир A: SSR plain-GET (резидентний IP).

Розвідка 2026-07-19: /smartphone/ SSR-ить 48 карток, 54 SM-коди. Ціна знижкового
товару крамить стару+поточну в одному .loop__price (`<del>стара</del><div>поточна</div>`),
тому del ВИДАЛЯЄМО перед читанням поточної:

    <div class="loop">
      <a href="/goods/smartfon_samsung_..._sm_s948bzkgeuc.html">
      <div class="loop__title">Смартфон Samsung Galaxy S26 Ultra 12/512GB Black (SM-S948BZKGEUC)</div>
      <div class="loop__price loop__price-promo"><del>70 999</del><div>65 299 грн</div></div>

MPN у назві (дужки) → матчинг T15. З ДЦ 403 → сателітне (телефон).
"""
from __future__ import annotations

from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://ktc.ua"


class KtcAdapter:
    source_name = "KTC"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css("div.loop"):
            title_node = card.css_first(".loop__title")
            title = title_node.text(strip=True) if title_node else ""
            if not title:
                continue

            a = card.css_first('a[href*="/goods/"]')
            href = (a.attributes.get("href") or "").split("?")[0].split("#")[0] if a else ""
            if not href.endswith(".html"):
                continue
            url = href if href.startswith("http") else BASE + href

            price_box = card.css_first(".loop__price")
            if price_box is None:
                continue
            del_node = price_box.css_first("del")
            old_kop = parse_price_to_kop(del_node.text()) if del_node else None
            if del_node is not None:
                del_node.decompose()          # прибрати стару → лишиться лише поточна
            now_kop = parse_price_to_kop(price_box.text())
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            ext = canon_ref(urlsplit(url).path)   # /goods/<slug>.html — стабільний ключ (§4.8)
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
                image_url=None,               # фото KTC lazy/стікери — не беремо (плейсхолдер у застосунку)
                discount_pct=pct,
            ))
        return items
