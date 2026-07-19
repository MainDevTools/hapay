"""Адаптер Brain (brain.com.ua) — лістинги категорій. Тир B: SPA (ціни лише після JS).

Розвідка 2026-07-19: лістинг plain-GET віддає розмітку БЕЗ цін — вони мальовані
JavaScript-ом. Тому Brain збирається лише у WEBVIEW-режимі (телефон рендерить
сторінку як браузер → готовий HTML → сюди). Після рендеру дані найнадійніші в
DATA-АТРИБУТАХ кнопки «Купити» (не в «брудних» цінових спанах із розстрочкою):

    <div class="goods-block__item">
      <a href="…-p1267688.html"><img data-observe-src="…U107.jpg"></a>
      <a class="add br-bbb-f"
         data-name-ua="Мобільний телефон Samsung Galaxy A07 … (SM-A075FZKGSEK)"
         data-price="5499" data-without-discount-price="14999">Купити</a>

Ціни — цілі гривні (data-price). MPN у назві (Samsung/Apple) → матчинг T15.
Фото — з `data-observe-src` (lazy-load вказівник; §7.4).
"""
from __future__ import annotations

from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop


class BrainAdapter:
    source_name = "Brain"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css("div.goods-block__item"):
            buy = card.css_first("a[data-price]")
            if buy is None:
                continue
            title = (buy.attributes.get("data-name-ua") or buy.attributes.get("data-name") or "").strip()
            if not title:
                continue

            now_kop = parse_price_to_kop(buy.attributes.get("data-price"))
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна

            # data-without-discount-price: стара ціна; '0' або ≤ поточної → не знижка
            old_kop = parse_price_to_kop(buy.attributes.get("data-without-discount-price"))
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None

            a = card.css_first('a[href*="-p"][href$=".html"]') or card.css_first('a[href$=".html"]')
            url = (a.attributes.get("href") or "").split("?")[0].split("#")[0] if a else ""
            if not url.startswith("https://brain.com.ua/"):
                continue

            img = card.css_first("img[data-observe-src]")
            image_url = img.attributes.get("data-observe-src") if img else None
            if image_url and not image_url.startswith("https://"):
                image_url = None

            ext = canon_ref(urlsplit(url).path)   # /ukr/<slug>-pNNN — стабільний ключ (§4.8)
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
