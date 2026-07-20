"""Адаптер Eldorado (eldorado.ua) — лістинги категорій. Тир B: SPA + ЛІНИВІ ціни.

Розвідка 2026-07-20 (у справжньому браузері):
- plain-GET марний: сторінка малюється JS-ом → лише `mode="render"` (телефон рендерить
  у WebView і шле готовий HTML);
- ціни довантажуються, коли картка потрапляє у вьюпорт: БЕЗ прокрутки сторінка віддає
  32 товари й НУЛЬ цін, після прокрутки — ціни зʼявляються. Саме тому рендерер тепер
  скролить до стабілізації DOM;
- класи хешовані styled-components (`…-sc-vfsrh8-4 jUqRwo`) → селектори лише ПРЕФІКСНІ,
  як у Citrus. Хеш `jUqRwo` міняється між білдами, `Pricestyled__StyledCurrentPrice` — ні.

Розмітка картки:

    <article class="OfferTilestyled__StyledArticle-…">
      <span itemprop="sku">71477703</span>
      <a href="/uk/smartfon-oppo-reno-12-fs…/p71477703/">…</a>
      <span class="…GoodsDescriptionstyled__StyledTypography-…" title="Смартфон OPPO …">
      <div class="Pricestyled__StyledOldPrice-…">10 999&nbsp;грн.</div>      ← лише при знижці
      <div class="Pricestyled__StyledCurrentPrice-…">9 999&nbsp;грн.</div>

⚠ ПАСТКА: поруч лежить блок розстрочки `Pricestyled__StyledPartpayInfo` з текстом
«від 1 200 грн.» — це платіж, НЕ ціна (наш parse_price_to_kop зчитав би його як 1200).
Тому ціну беремо ТІЛЬКИ з StyledCurrentPrice/StyledOldPrice, ніколи з блоку цілком.

Позиції «Продано»/«Незабаром» цін не мають (кнопка «Повідомити») — пропускаємо їх,
як і всюди: без поточної ціни позиція нам не потрібна. На лістингу таких ~2/3.

Фото: у розмітці лістинга його немає (картинка малюється скриптом) → image_url=None;
застосунок покаже плейсхолдер. Байти чужих фото ми й так ніколи не зберігаємо (§7.4).
"""
from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, parse_price_to_kop

BASE = "https://eldorado.ua"
# /uk/<slug>/p71477703/ — числовий id товару; стабільний ключ (§4.8), не залежить від
# мовного префікса (/uk/ vs без нього) і від слага, який крамниця може переписати
_PID = re.compile(r"/p(\d+)/?$")


class EldoradoAdapter:
    source_name = "Eldorado"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css('article[class*="OfferTilestyled__StyledArticle"]'):
            # ціна — ТІЛЬКИ з власного вузла (поруч розстрочка «від 1 200 грн.»)
            cur = card.css_first('[class*="Pricestyled__StyledCurrentPrice"]')
            if cur is None:
                continue                      # «Продано»/«Незабаром» — без ціни, пропускаємо
            now_kop = parse_price_to_kop(cur.text())
            if not now_kop:
                continue

            title_node = card.css_first('[class*="GoodsDescriptionstyled__StyledTypography"]')
            if title_node is None:
                continue
            # назва є і в атрибуті title, і текстом — атрибут надійніший (без обрізання)
            title = (title_node.attributes.get("title") or title_node.text() or "").strip()
            if not title:
                continue

            old_node = card.css_first('[class*="Pricestyled__StyledOldPrice"]')
            old_kop = parse_price_to_kop(old_node.text()) if old_node is not None else None
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # не знижка

            href = ""
            for a in card.css("a[href]"):
                h = (a.attributes.get("href") or "").split("#")[0].split("?")[0]
                if _PID.search(h):
                    href = h
                    break
            m = _PID.search(href)
            if not m:
                continue
            ext = f"p{m.group(1)}"            # ключ = id товару
            if ext in seen:                   # дедуп у межах сторінки (§10.1)
                continue
            seen.add(ext)

            url = href if href.startswith("http") else BASE + href
            pct = round((1 - now_kop / old_kop) * 100) if old_kop else None

            items.append(RawItem(
                external_ref=ext,
                url=url,
                title=title,
                price_now_kop=now_kop,
                price_old_kop=old_kop,
                in_stock=True,                # без ціни ми сюди не доходимо
                image_url=None,               # у лістингу фото немає (малює скрипт)
                discount_pct=pct,
            ))
        return items
