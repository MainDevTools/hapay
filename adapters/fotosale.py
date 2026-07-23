"""Адаптер Fotosale (fotosale.ua) — лістинг категорії. Тир D: CSS, семантичні класи.

Розвідка 2026-07-23. Фотоспеціаліст — розділ «Фото-відео» (фотоапарати,
екшн-камери GoPro) + карти пам'яті. Класичний server-side HTML (без JS-фреймворка),
burst 200×3, robots дозволяє (disallow лише /search/, /order=*, кошик).

    <div class="product-one">
      <div class="image"><a href="https://fotosale.ua/ua/product_N66086.htm" class="img">
        <img class="v lazyload" data-src="https://fotosale.ua/images/products/66/….jpg"
             title="Canon Фотокамера Canon EOS R3 (4895C014) (UA)"></a></div>
      <div class="product-name">
        <a class="name" href="https://fotosale.ua/ua/product_N66086.htm">Фотокамера Canon EOS R3 (4895C014) (UA)</a>
        <div class="product-id">Код:&nbsp;<span>47626</span></div></div>
      <div class="prices"><div class="price">
        <span class="main-price">64 999 <span class="grn">грн</span></span>
        <span class="old-price">69999 <span class="grn">грн</span></span>   ← лише на акційних

Нюанси:
- Назва — з a.name (чиста); img[title] має префікс бренду («Canon Фотокамера Canon…») —
  НЕ брати, дублює бренд і засмічує матчер.
- Зображення лениве: URL у data-src (не src — там заглушка); беремо data-src, fallback src.
- Пагінація: ?page=2 і /page2 віддають 200 і ТІ САМІ товари (перетин 20/20, нових 0 —
  перевірено фактом) → page_tpl НЕМАЄ, кожен лістинг = top-20.
- Дрони: обидві рубрики (rub3841, rub3128) порожні — категорію НЕ реєструємо.
- Ціни інколи без пробілів-роздільників («69999») — parse_price_to_kop справляється.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://fotosale.ua"


class FotosaleAdapter:
    source_name = "Fotosale"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for box in tree.css("div.product-one"):
            a = box.css_first(".product-name a.name")
            if a is None:
                continue
            href = a.attributes.get("href") or ""
            if "product_" not in href:
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            title = (a.text() or "").strip()
            cur = box.css_first(".price .main-price")
            old = box.css_first(".price .old-price")
            now_kop = parse_price_to_kop(cur.text() if cur is not None else None)
            old_kop = parse_price_to_kop(old.text() if old is not None else None)
            if not title or now_kop is None:
                continue
            image = None
            img = box.css_first(".image img")
            if img is not None:
                s = img.attributes.get("data-src") or img.attributes.get("src") or ""
                if s.startswith("http"):
                    image = s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=old_kop,
                               image_url=image))
        return out
