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

import re
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

# Мініатюри товарів лежать на окремому хості; стікери й банери — на ktc.ua/imgd,
# і саме через них фото колись визнали «непридатними».
IMG_HOST_RE = re.compile(r"^https://img\.ktc\.ua/")

BASE = "https://ktc.ua"


def _image_of(card) -> str | None:
    """Фото товару з картки лістинга (інв. B — беремо лише ВКАЗІВНИК, не байти).

    ⚠ Довго стояло `image_url=None` з поміткою «фото KTC lazy/стікери». Помітка була
    напівправдою: в `<img src>` справді стікери (`ktc.ua/imgd/stickers/…`), але сама
    мініатюра лежить у `<picture><source srcset>` на `img.ktc.ua`. Наслідок побачили
    аж на сайті 2026-07-26: 2405 із 2405 товарів KTC без фото, третина стрічки —
    плейсхолдери.

    Беремо саме `source[srcset]`, а не `data-images`: другий — це ВСЯ галерея товару,
    і її перший кадр не збігається з тим, що крамниця показує в лістингу."""
    node = card.css_first("picture source[srcset]")
    if node is None:
        return None
    # srcset може нести дескриптори («url 2x, url2 3x») — беремо перший URL
    raw = (node.attributes.get("srcset") or "").strip()
    url = raw.split(",")[0].strip().split(" ")[0]
    if not url.startswith("https://") or not IMG_HOST_RE.match(url):
        return None                       # стікери/банери з іншого хоста — не фото товару
    return url


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
                image_url=_image_of(card),
                discount_pct=pct,
            ))
        return items
