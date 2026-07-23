"""Адаптер Med-magazin (med-magazin.ua) — лістинг категорії. Тир D: CSS, семантичні класи.

Розвідка 2026-07-23. Спеціаліст медтехніки — повна синергія з розділом «Медтехніка»
(тонометри/глюкометри/небулайзери/пульсоксиметри/термометри). SSR plain-GET,
burst 200×3, robots дозволяє. Розмітка приємно семантична (жодних хешів):

    <div class="product-box-container ">        ← головна сітка (є ще slider-варіант!)
      <div class="product-box">
        <div class="articul">Код: 49633</div>
        <a class="product-images" href="/ua/item_n42533.htm"><picture>…<img src="https://cdn.med-magazin.ua/…"></a>
        <div class="name-container"><a href="/ua/item_n42533.htm">Автоматичний тонометр B.Well MED-50 (Швейцарія)</a></div>
        <div class="price">
          <div class="current">1489 <span>грн</span></div>
          <div class="old">2232 <span>грн</span></div>     ← лише на акційних

⚠ ДВІ ПАСТКИ:

1. Клас `product-box-container` НОСЯТЬ І СЛАЙДЕРИ «рекомендоване»: на сторінці
   категорії 57 карток, з них лише 20 — головна сітка, а 37 — `scroller-item`
   (рекомендовані товари З ІНШИХ категорій). Брати всі — означає тегувати чужі
   товари нашою категорією. Фільтруємо картки, чий контейнер несе `scroller-item`.

2. Пагінація — Vue/AJAX: `?page=2` віддає 200 і ТІ САМІ 20 карток (перетин 20/20,
   нових 0 — перевірено фактом). Тому page_tpl НЕМАЄ, кожен лістинг = top-20.
   Компенсуємо ПІДТИПАМИ крамниці: тонометри = 3 категорії (авто/зап'ястя/напівавто),
   небулайзери = 2 (компресорні/МЕШ) — разом покриття ширше за одну сторінку.

Наявність: блок `.stock .available` («в наявності») — якщо його нема, товар
навряд у головній сітці, але тримаємо дефолт True. MPN у назвах рідкий
(«B.Well MED-50» — модель є, бренв дрібний) → цінність per-store Omnibus.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://med-magazin.ua"


class MedmagazinAdapter:
    source_name = "MedMagazin"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for box in tree.css("div.product-box-container"):
            cls = box.attributes.get("class") or ""
            if "scroller-item" in cls:           # пастка 1: слайдери «рекомендоване»
                continue
            a = box.css_first(".name-container a")
            if a is None:
                continue
            href = a.attributes.get("href") or ""
            if "/item_" not in href:
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            title = (a.text() or "").strip()
            cur = box.css_first(".price .current")
            old = box.css_first(".price .old")
            now_kop = parse_price_to_kop(cur.text() if cur is not None else None)
            old_kop = parse_price_to_kop(old.text() if old is not None else None)
            if not title or now_kop is None:
                continue
            image = None
            img = box.css_first("picture img") or box.css_first("img")
            if img is not None:
                s = img.attributes.get("src") or ""
                if s.startswith("http"):
                    image = s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=old_kop,
                               image_url=image))
        return out
