"""Адаптер Zootovary (zootovary.ua) — лістинг категорії. Тир D: CSS, семантичні класи.

Розвідка 2026-07-23. Зоо-спеціаліст — розділ «Зоотовари»: корми сухі/консерви для
котів і собак + амуніція. Класичний server-side HTML (osCommerce-родовід, категорії
`…-c-NN_NN.html`), burst 200×3, robots дозволяє, пагінація СПРАВЖНЯ: `?page=2`
віддає нові товари (34/34 нових — перевірено фактом) → page_tpl у реєстрації.

    <div class="product" data-pid="4959">
      …
      <a href="https://zootovary.ua/uk/royal-canin/…-p-4959.html" class="model_product">
        Royal Canin Sterilised 37 Сухий корм для стерилізованих кішок</a>
      …
      <p class="price">
        <span class="new_price color_red"><span class="ccp">від</span> 212 <span class="ccp">₴</span></span>
        <span class="old_price">250 <span class="ccp">₴</span></span></p>

Нюанси:
- Ціна «від N ₴» — мінімальна серед ВАГОВИХ варіантів (корм 400 г / 2 кг / 10 кг).
  Беремо як є: це і є показувана лістингова ціна; порівнюється сама з собою в часі
  (per-store Omnibus), тож «від»-семантика стабільна. Слово «від» і «₴» живуть в
  окремих span.ccp — text() віддає «від 212 ₴», parse_price_to_kop чистить сам.
- ⚠ КОМА — РОЗДІЛЬНИК ТИСЯЧ: «2,739 ₴» = 2739 грн (не 2.74!). Глобальний
  parse_price_to_kop трактує кому як десяткову (так у інших крамниць) — тому тут
  чистимо коми-тисячники ЛОКАЛЬНО перед парсом (впіймано на валідації: собачий корм
  віддавав 274 коп і 5 «нісенітниць» old<now). Кома лишається десятковою, якщо після
  неї не рівно 3 цифри — «212,50» не зачепить.
- Зображення ленине І відносне: у src — заглушка pixel_trans.png, справжній шлях у
  data-original БЕЗ хоста («getimage/products/…») → клеїмо до BASE.
- Селектор кореня — токен `product` (клас рівно "product"); сусідні
  col_product/wrapper_product_hover — інші токени, не матчаться.
- Шампуні для котів/псів окремої категорії НЕ мають (лише мішаний «грумінг») —
  ці наші слаги тут не реєструємо.
- Матчер очікувано слабкий: назви кормів описові (бренд + діета + вага) —
  цінність = per-store Omnibus + четверте зоо-джерело поруч із загальними.
"""
from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://zootovary.ua"

_THOUSANDS_COMMA = re.compile(r",(?=\d{3}\b)")


def _price(node) -> int | None:
    if node is None:
        return None
    return parse_price_to_kop(_THOUSANDS_COMMA.sub("", node.text()))


class ZootovaryAdapter:
    source_name = "Zootovary"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for box in tree.css("div.product"):
            a = box.css_first("a.model_product")
            if a is None:
                continue
            href = a.attributes.get("href") or ""
            if "-p-" not in href:
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            title = (a.text() or "").strip()
            now_kop = _price(box.css_first(".price .new_price"))
            old_kop = _price(box.css_first(".price .old_price"))
            if not title or now_kop is None:
                continue
            image = None
            img = box.css_first("img")
            if img is not None:
                s = img.attributes.get("data-original") or ""
                if s and "pixel_trans" not in s:
                    image = s if s.startswith("http") else f"{BASE}/{s.lstrip('/')}"
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=old_kop,
                               image_url=image))
        return out
