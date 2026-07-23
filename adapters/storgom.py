"""Адаптер Storgom (storgom.ua) — лістинг категорії. Тир B/D гібрид: JSON-LD ItemList
дає назву+URL, ціни — CSS по картках (LD цін не несе).

Розвідка 2026-07-23. Спеціаліст інструмент/сад — найвищий профільний перетин з нашими
розділами «Інструменти» + «Садова техніка» (20 з 22 категорій знайдено; зварювальних
і мийок ВТ окремих категорій не знайшли). SSR plain-GET, burst 200×3, robots дозволяє.

    <script type="application/ld+json">[…, {"@type":"ItemList","itemListElement":[
      {"@type":"ListItem","position":1,"url":"https://storgom.ua/ua/product/procraft-190392.html",
       "name":"Перфоратор PROCRAFT BH1400 (014001)"}, …]}, …]</script>

    <div class="products-list_item-wrap">
      <a href="/ua/product/procraft-190392.html" …>
      <div class="price-wrapper …">
        <div class="price d-flex flex-v-center">
          <!-- акційна картка: -->
          <div class="old-price …"><s>8 999</s><span class="diff">-2 100 ₴</span></div>
          <div class="new-price">6 899 <span class="cur">₴</span></div>
          <!-- звичайна картка: БЕЗКЛАСОВИЙ div -->
          <div>2 475 <span class="cur">₴</span></div>

⚠ ДВІ ПАСТКИ (та сама хвороба, що в Telemart, — тихо криві дані, не помилка):

1. `.price` .text() СКЛЕЮЄ всі числа: стару, бейдж «-2 100 ₴» і нову → «8999-2100₴6899»
   парсилось би в багатотрильйонні копійки. Перша проба саме це й віддала
   (now=89992100689900). Тому: акційна → лише `.new-price`; звичайна → перший
   БЕЗКЛАСОВИЙ `<div>` усередині `.price`.

2. `.old-price` містить і `<s>8 999</s>`, і бейдж різниці `-2 100 ₴` — .text() вузла
   склеїв би їх. Берімо лише дочірній `<s>`.

Пагінація: `/ua/<slug>/page-N` — ГОЛА форма слага без `.html` і без хвостового «/»
працює для всіх категорій (перевірено фактом: болгарки/дискові/мотокоси — стор.2
перетин 0). Канонічні URL крамниці різняться (де-не-де `.html`, де-не-де «/»), але
гола форма віддає ті самі 40 позицій — тому в конфізі тримаємо ЇЇ, інакше потрібні
були б три різні page_tpl.

Наявність лістинг не показує — вважаємо в наявності (як Telemart). MPN у частини
назв у дужках («(014001)» — артикул продавця, не MPN виробника) → матчер слабкий,
заміряно 7/40; цінність — per-store Omnibus.
"""
from __future__ import annotations

import json

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://storgom.ua"


class StorgomAdapter:
    source_name = "Storgom"

    @staticmethod
    def _ld_names(tree) -> dict[str, str]:
        """ItemList JSON-LD → {canon_ref(url): name}. Назви тут чистіші за alt картинок."""
        names: dict[str, str] = {}
        for node in tree.css('script[type="application/ld+json"]'):
            try:
                data = json.loads(node.text())
            except (ValueError, TypeError):
                continue
            for d in data if isinstance(data, list) else [data]:
                if isinstance(d, dict) and d.get("@type") == "ItemList":
                    for el in d.get("itemListElement", ()):
                        u, n = el.get("url"), el.get("name")
                        if u and n:
                            names[canon_ref(u)] = n.strip()
        return names

    @staticmethod
    def _prices(card) -> tuple[int | None, int | None]:
        """(поточна, стара). Пастки 1–2 з шапки: new-price/безкласовий div; old лише <s>."""
        new = card.css_first(".new-price")
        if new is not None:
            olds = card.css_first(".old-price s")
            return (parse_price_to_kop(new.text()),
                    parse_price_to_kop(olds.text() if olds is not None else None))
        price = card.css_first(".price")
        if price is None:
            return None, None
        for child in price.css("div"):
            if not (child.attributes.get("class") or "").strip():
                return parse_price_to_kop(child.text()), None
        return None, None

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        names = self._ld_names(tree)
        out: list[RawItem] = []
        seen: set[str] = set()
        for card in tree.css("div.products-list_item-wrap"):
            a = card.css_first('a[href*="/ua/product/"]')
            if a is None:
                continue
            href = a.attributes.get("href") or ""
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            title = names.get(ref) or (a.attributes.get("title") or "").strip()
            if not title:
                img = card.css_first("img")
                title = (img.attributes.get("alt") or "").strip() if img is not None else ""
            now, old = self._prices(card)
            if not title or now is None:
                continue
            image = None
            for im in card.css("img"):
                s = im.attributes.get("src") or im.attributes.get("data-src") or ""
                if s and "/theme/" not in s and not s.endswith(".svg"):
                    image = s if s.startswith("http") else BASE + s
                    break
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now, price_old_kop=old,
                               image_url=image))
        return out
