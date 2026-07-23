"""Адаптер Antoshka (antoshka.ua) — лістинг категорії. Тир D: CSS, семантичні класи.

Розвідка 2026-07-23. Дитяча мережа — ПЕРШИЙ спеціаліст розділу «Дитячі товари»
(7/7 наших слагів). Magento, SSR plain-GET, burst 200×3, robots дозволяє
(disallow лише checkout/customer/search), пагінація `?p=2` (Magento-стандарт).

    <a href="https://antoshka.ua/uk/proguljankova-koljaska-cybex-beezy-fog-grey.html"
       class="product-catalog products-catalog__product …">
      … <img … alt="Прогулянкова коляска Cybex Beezy Fog Grey">
      <div class="product-catalog__prices">
        <div class="product-catalog__price">
          <p class="d-flex align-items-end"> 9 999 <span>₴</span> </p>
          <div class="promo promo-new">-22%</div>                    ← ПАСТКА
        </div>
        <div class="product-catalog__price-old">
          <div class="promo promo-old">-22%</div>                    ← ПАСТКА
          <span>12 899 ₴</span>
        </div></div>

⚠ ГОЛОВНА ПАСТКА: у цінових контейнерах сидять promo-бейджі «-22%». Взяти текст
контейнера цілком — отримати «-22% 12 899 ₴», звідки парсер вихопить 22.
Тому беремо ЛИШЕ внутрішні вузли: now — <p> усередині __price, old — <span>
усередині __price-old.

Нюанси:
- Якір <a> — САМ корінь картки (клас product-catalog); href абсолютний .html.
- Назва — з img[alt] (чиста «Прогулянкова коляска Cybex Beezy Fog Grey»).
- Ціни «9 999 ₴» — пробіл-тисячник, без копійок.
- Категорія стерилізаторів у крамниці мішана («Підігрівачі та стерилізатори») —
  реєструємо як є, чесно закоментовано в конфігу.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://antoshka.ua"


class AntoshkaAdapter:
    source_name = "Antoshka"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for a in tree.css("a.product-catalog"):
            href = a.attributes.get("href") or ""
            if not href.endswith(".html"):
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            img = a.css_first("img")
            title = ((img.attributes.get("alt") or "").strip()
                     if img is not None else "")
            # пастка promo-бейджів: лише внутрішні вузли, не контейнери
            p = a.css_first(".product-catalog__price p")
            olds = a.css_first(".product-catalog__price-old span")
            now_kop = parse_price_to_kop(p.text() if p is not None else None)
            old_kop = parse_price_to_kop(olds.text() if olds is not None else None)
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
