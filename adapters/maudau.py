"""Адаптер MAUDAU (maudau.com.ua) — лістинг категорії. Тир D: CSS по data-testid.

Розвідка 2026-07-23 (другий захід; перший, тижнем раніше, закінчився вердиктом
«SPA без render» — ЗАСТАРІВ: зараз Next.js SSR віддає повний лістинг із цінами
plain-GET'ом стабільно, 3×872KB без анти-бота). Маркетплейс; вхід — 7 категорій
«Дитячих товарів» (спадок Pampik: pampik.com тепер редіректить сюди).

Tailwind-класи хешовано-непридатні, АЛЕ розмітка щедро розмічена data-testid —
найстабільніший вид гачків (їх тримають для авто-тестів самої крамниці):

    <div data-testid="productItem">
      …<a … href="https://maudau.com.ua/product/koliaska-balios-…">
      <img data-testid="productImage" …>
      <p data-testid="productName">Коляска Cybex Balios S Lux … (524001179)</p>
      <p data-testid="productFullPrice" class="… line-through">21 700 ₴</p>  ← стара
      <p data-testid="finalPrice">18 445 ₴</p>                               ← поточна

Нюанси:
- Назви мають SKU в дужках («(524001179)») — MPN-дружні для матчера.
- Пагінація КЛІЄНТСЬКА: ?page=2 віддає ті самі 57 товарів (звірено SKU двічі —
  урок Eldorado) → pages=1, top-~50/категорію.
- Ціни «21 700 ₴» — пробіл-тисячник; parse_price_to_kop справляється.
- href бувають абсолютні й відносні — нормалізуємо до BASE.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://maudau.com.ua"


class MaudauAdapter:
    source_name = "MAUDAU"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for box in tree.css('[data-testid="productItem"]'):
            a = None
            for cand in box.css("a"):
                if "/product/" in (cand.attributes.get("href") or ""):
                    a = cand
                    break
            if a is None:
                continue
            href = a.attributes.get("href") or ""
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            name = box.css_first('[data-testid="productName"]')
            title = (name.text() or "").strip() if name is not None else ""
            cur = box.css_first('[data-testid="finalPrice"]')
            old = box.css_first('[data-testid="productFullPrice"]')
            now_kop = parse_price_to_kop(cur.text() if cur is not None else None)
            old_kop = parse_price_to_kop(old.text() if old is not None else None)
            if not title or now_kop is None:
                continue
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None
            image = None
            img = box.css_first('[data-testid="productImage"]') or box.css_first("img")
            if img is not None:
                s = img.attributes.get("src") or ""
                if s.startswith("http"):
                    image = s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=old_kop,
                               image_url=image))
        return out
