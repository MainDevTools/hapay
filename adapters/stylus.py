"""Адаптер Stylus (stylus.ua) — лістинг категорії. Тир D: DOM-картки; LD — лише розвідка.

Розвідка 2026-07-23. Електроніка (сильноматчерні категорії). Next.js App Router
(streaming hydration `self.__next_f`), SSR plain-GET, burst 200×3, robots дозволяє.

⚠ ГОЛОВНЕ ОБМЕЖЕННЯ: SSR рендерить ЛИШЕ першу сторінку — /page-2/, ?p=2, ?page=2
віддають 200 і ті самі ~30 карток (перевірено фактом: перетин 30/30). Тому pages=1,
джерело дає top-30 кожної категорії. Це свідомо прийнято: топ-моделі — саме те, що
порівнюється крос-крамнично.

Чому DOM, а не JSON-LD (хоч LD на сторінці є і structured-data-first — інваріант D):
LD Product.offers[] несе name/price/url/availability, АЛЕ (1) БЕЗ старої ціни — а
заявлена стара ціна нам потрібна для Omnibus-перевірки; (2) url веде на stls.store —
альтернативний домен крамниці, а не stylus.ua. LD використано як ВЕРИФІКАЦІЮ правила
цін при розвідці: LD price == min(DOM-ціни) на 30/30 картках без розбіжностей.

    <a class="sc-4b36cc3-1 fniZIJ product-list-item" href="/uk/…-p1451274c11256.html">
      <img … title="Смартфон Xiaomi Redmi Note 15 6/128GB Black (Global, NFC)"
             alt="…: Дисплей 6.77&quot; AMOLED …">
      …
      <div class="sc-213cc62e-2 hQQheL">9 959 грн</div>   ← стара (хешований клас!)
      <div class="sc-213cc62e-3 jnhkys">8 299 грн</div>   ← поточна (хешований клас!)

⚠ ДВІ ПАСТКИ:

1. Класи цін ХЕШОВАНІ styled-components (sc-213cc62e-2/hQQheL) — зміняться будь-яким
   білдом крамниці. Селектор по них — міна сповільненої дії. Тому ціни беремо
   regex-ом «N грн» з ТЕКСТУ картки: now=min, old=max (якщо >min). Правило
   верифіковано LD-цінами 30/30; лічильник бонусів («1») без «грн» — не матчиться.

2. `title` картинки — чиста назва; `alt` — назва + хвіст характеристик
   («…: Дисплей 6.77"…»). Плутати не можна: alt засмічує матчер.

3. Regex по СКЛЕЄНОМУ тексту картки (a.text()) — тихо криві старі ціни: лічильник
   відгуків стоїть у DOM одразу перед старою ціною, і «1» + «9 959 грн» зливаються
   в «19 959 грн» (впіймано на валідації: Xiaomi old=19 959 замість 9 959; Samsung
   old=1 159 999 замість 59 999 — приклеївся лічильник «11»). Мінімальна ціна
   неушкоджена (LD-звірка 30/30 це маскувала!), страждає лише old. Тому ціни
   беремо з HTML якорено на ПОЧАТОК текстового вузла: `>N грн`.

Стабільні гачки: токен `product-list-item` у класі <a> (єдиний нехешований) та
`img[title]`. Наявність лістинг не показує — вважаємо в наявності.
"""
from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://stylus.ua"

# «>» — межа текстового вузла: число мусить ПОЧИНАТИ вузол (пастка 3 — лічильник
# відгуків у сусідньому div приклеюється зліва при конкатенації тексту).
_PRICE_RE = re.compile(r">\s*([\d][\d\s   ]{0,14})\s*грн")


class StylusAdapter:
    source_name = "Stylus"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for a in tree.css("a.product-list-item"):
            href = a.attributes.get("href") or ""
            if not href:
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            img = a.css_first("img")
            title = ((img.attributes.get("title") or "").strip()
                     if img is not None else "")
            if not title and img is not None:            # запасний хід: alt до «: »
                title = (img.attributes.get("alt") or "").split(": ")[0].strip()
            # a.html СЕРІАЛІЗУЄ nbsp назад у сутність «&nbsp;» — розгорнути до regex,
            # інакше [\d\s]-клас не бачить «9&nbsp;959» і всі ціни мовчки зникають.
            raw = (a.html or "").replace("&nbsp;", " ").replace("&#160;", " ")
            prices = [p for p in (parse_price_to_kop(m)
                                  for m in _PRICE_RE.findall(raw))
                      if p]
            if not title or not prices:
                continue
            now = min(prices)
            old = max(prices) if max(prices) > now else None
            image = None
            if img is not None:
                s = img.attributes.get("src") or ""
                if s.startswith("http"):
                    image = s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now, price_old_kop=old,
                               image_url=image))
        return out
