"""Адаптер Autopresent (autopresent.com.ua) — лістинг категорії. Тир D: CSS.

Розвідка 2026-07-23. Спеціаліст авто-електроніки — розділ «Авто»: відеореєстратори,
автомагнітоли (компресорів/пилососів/холодильників крамниця не тримає — 2/5 наших
авто-слагів). OpenCart/Journal3, burst 200×3, robots дозволяє (route=-сміття закрите).

    <div class="main-products product-grid">          ← ГОЛОВНА сітка
      <div class="product-thumb">
        <a href="https://autopresent.com.ua/ua/…/videoregistrator-playme-go" class="product-img">
          <img … title="Playme GO" alt="<b>Notice</b>: Undefined index: model in …"/></a>
        …
        <div class="price">
          <span class="price-old">43999 грн.</span>
          <span class="price-new">27999 грн.</span>
          <span class="price-tax">Без ПДВ:27999 грн.</span></div>

⚠ ТРИ ПАСТКИ:

1. Блоки «спецпропозицій» (module-products-N) ТЕЖ містять .product-thumb з товарами
   З ІНШИХ категорій (сигналізація в лістингу реєстраторів; 6 з 18 карток на
   сторінці). Скоупимось до контейнера .main-products — інакше тегуємо чуже.

2. alt зображень БИТИЙ — містить PHP Notice («Undefined index: model in …tpl»)
   прямо в атрибуті. Назва — з img[title] (чиста) або текст лінка .name.

3. Усередині .price сидить .price-tax («Без ПДВ:27999 грн.») — текст .price цілим
   брати не можна (задвоєні числа). Лише вузли .price-new/.price-old; для карток
   без знижки — текст .price з ВИРІЗАНИМИ tax/old вузлами, перше «N грн».

Ціни «43999 грн.» — без роздільників. Пагінації в лістингу нема (12 карток у
сітці) → top-12/категорію.
"""
from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://autopresent.com.ua"

_FIRST_PRICE = re.compile(r"([\d][\d\s   ]{0,12})\s*грн")


class AutopresentAdapter:
    source_name = "Autopresent"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        main = tree.css_first(".main-products")
        if main is None:                      # пастка 1: без сітки нічого не беремо
            return out
        for box in main.css("div.product-thumb"):
            a = box.css_first("a.product-img")
            if a is None:
                continue
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
            if not title:
                name = box.css_first(".name a") or box.css_first("h4 a")
                title = (name.text() or "").strip() if name is not None else ""
            price = box.css_first(".price")
            if price is None:
                continue
            new = price.css_first(".price-new")
            old = price.css_first(".price-old")
            if new is not None:
                now_kop = parse_price_to_kop(new.text())
            else:
                # без знижки: текст .price мінус tax/old вузли, перше «N грн»
                txt = price.text()
                for sub in (price.css_first(".price-tax"),):
                    if sub is not None:
                        txt = txt.replace(sub.text(), "")
                m = _FIRST_PRICE.search(txt)
                now_kop = parse_price_to_kop(m.group(1)) if m else None
            old_kop = parse_price_to_kop(old.text()) if old is not None else None
            if not title or now_kop is None:
                continue
            image = None
            if img is not None:
                s = img.attributes.get("src") or ""
                if s.startswith("http"):
                    image = s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=old_kop,
                               image_url=image))
        return out
