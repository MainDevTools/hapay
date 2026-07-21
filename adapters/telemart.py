"""Адаптер Telemart (telemart.ua) — лістинг категорії. Тир D: CSS по класах, SSR plain-GET.

Розвідка 2026-07-21. На відміну від Епіцентру й Венкона, розмітки schema.org тут
НЕМАЄ зовсім (`schema.org/Product` — нуль входжень), тож екстракція йде нижнім тиром
порядку (§8.4) — по класах. Це прийнято свідомо: клас-селектори крихкі до редизайну,
але крамниця того варта. Заміряно ДО роботи: 76% товарів у ТВ і 93% у ноутбуках несуть
артикул у назві, а 66 із 83 артикулів (80%) уже є в нашому каталозі — найвищий перетин
з усіх крамниць, які ми додавали (Епіцентр 71%, Венкон 39%). Частина позицій одразу
потрапляє в групи на дев'ять крамниць.

    <div class="product-item__inner product_wrapper">
      <img src="https://img.telemart.ua/…/philips-43-43pus700012…">
      <div class="product-item__title">
        <a href="https://telemart.ua/products/philips-43-43pus700012-black/"
           title="Телевизор Philips 43&quot; 43PUS7000/12 Black">…</a>
      <div class="product-item__footer">
        <div class="product-cost product-cost_old">17 499 <span>₴</span></div>
        <div class="product-cost product-cost_discount">-14%</div>
        <div class="product-cost product-cost_new">14 999 <span>₴</span></div>

⚠ ТРИ ПАСТКИ, кожна дає не помилку, а тихо криві дані:

1. Клас `product-cost` НОСЯТЬ ОДРАЗУ ТРИ вузли: стара ціна, поточна і бейдж «-14%».
   Селектор `.product-cost` без модифікатора віддав би перший-ліпший — тобто СТАРУ
   ціну як поточну, і всі знижки рахувались би від неправильного числа. Беремо лише
   `_new` / `_old`.

2. Перше `<img>` у картці — НЕ фото товару, а іконка «безкоштовна доставка»
   (`/theme/main/i/free-delivery.svg`); далі йдуть логотипи банків для розстрочки.
   Тому пропускаємо все під `/theme/`.

3. На сторінці живе випадаюче меню пошуку (`search__list-products`) зі СВОЇМИ
   картками й тим самим класом `product-cost`. Через це рахунок «товарів на сторінці»
   легко завищити. Рятує прив'язка до `.product-item__inner` — сітка каталогу.

Пагінація — `?page=N` (перевірено фактом: стор.2 → 48 інших карток, перетин із
першою нульовий). Наявність у лістингу не показують — вважаємо в наявності.
MPN у назві → матчинг T15.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://telemart.ua"


class TelemartAdapter:
    source_name = "Telemart"

    @staticmethod
    def _prices(card) -> tuple[int | None, int | None]:
        """(поточна, стара) з підвалу картки.

        ⚠ ПАСТКА, що коштувала половини каталогу. Модифікатор `_new` крамниця ставить
        ЛИШЕ на акційних товарах; у звичайного товару ціна лежить у голому
        `.product-cost` без модифікатора. Перша версія брала тільки `_new` і тихо
        віддавала 25 позицій із 48 — причому всі 25 зі знижкою. Виглядало б цілком
        правдоподібно («Telemart торгує переважно акційним»), тож помітити було б
        нічим, окрім лічильника.

        Тому класифікуємо КОЖЕН `.product-cost` за модифікатором, а не шукаємо один.
        """
        now = old = None
        for node in card.css(".product-cost"):
            cls = node.attributes.get("class") or ""
            if "product-cost_discount" in cls:
                continue                      # бейдж «-14%», не ціна
            if "product-cost_old" in cls:
                old = parse_price_to_kop(node.text())
            elif now is None:                 # `_new` або голий `.product-cost`
                now = parse_price_to_kop(node.text())
        return now, old

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css(".product-item__inner"):
            a = card.css_first(".product-item__title a")
            if a is None:
                continue
            # title атрибута: у тексті лапки й діагоналі крамниця подає як entity
            title = " ".join((a.attributes.get("title") or a.text(strip=True)).split())
            if not title:
                continue

            href = (a.attributes.get("href") or "").split("?")[0].split("#")[0]
            if not href:
                continue
            url = href if href.startswith("http") else BASE + href

            now_kop, old_kop = self._prices(card)
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            image_url = None
            for im in card.css("img"):        # перше фото, що НЕ іконка теми (пастка 2)
                src = im.attributes.get("src") or im.attributes.get("data-src") or ""
                if src and "/theme/" not in src:
                    image_url = src if src.startswith("http") else BASE + src
                    break

            ext = canon_ref(urlsplit(url).path)   # /products/<slug> — стабільний ключ (§4.8)
            if ext in seen:                       # дедуп у межах сторінки (§10.1)
                continue
            seen.add(ext)

            items.append(RawItem(
                external_ref=ext,
                url=url,
                title=title,
                price_now_kop=now_kop,
                price_old_kop=old_kop,
                image_url=image_url,
            ))
        return items
