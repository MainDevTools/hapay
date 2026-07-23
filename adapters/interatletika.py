"""Адаптер Interatletika (shop.interatletika.com) — лістинг категорії. Тир D: CSS.

Розвідка 2026-07-23. Спеціаліст тренажерів (виробник + рітейл) — розділ «Спорт»:
бігові доріжки, велотренажери. Bitrix (PAGEN_1-пагінація — справжня: стор.2 дає
22/24 нових, перевірено фактом), burst 200×3, robots: НУЛЬ disallow-правил.

    <div class="ia--card in-stock">
      …
      <div class="ia--card-name"><a href="/begovaya-dorozhka-toptrack-kd152d-a/">
        Бігова доріжка TopTrack KD152D-A </a></div>
      <div class="ia--card-price"><div class="coast">
        <div class="base">53 370 <span>₴</span></div></div>…

Нюанси:
- href ВІДНОСНИЙ від кореня (без /ua/) — клеїмо до BASE.
- Ціна «53 370 ₴» з пробілами-тисячниками; parse_price_to_kop чистить сам.
- Старої ціни на розвідці НЕ бачили ЖОДНОЇ (виробник, рівні ціни): old-селектор
  невідомий → price_old_kop=None завжди. Якщо крамниця почне показувати
  перекреслені ціни — розвідати заново, НЕ вгадувати селектор.
- Зображення відносне (/upload/resize_cache/…) — клеїмо до BASE; перший <img> у
  картці — 1×1 data:-заглушка (ia--fake-image), беремо .ia--real-image.
- Картки поза наявністю мають клас ia--card без in-stock — беремо всі ia--card
  (історія цін цінна і для тимчасово відсутніх), наявність не парсимо.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://shop.interatletika.com"


class InteratletikaAdapter:
    source_name = "Interatletika"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for box in tree.css("div.ia--card"):
            a = box.css_first(".ia--card-name a")
            if a is None:
                continue
            href = a.attributes.get("href") or ""
            if not href or href.startswith("#"):
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            title = (a.text() or "").strip()
            base = box.css_first(".ia--card-price .base")
            now_kop = parse_price_to_kop(base.text() if base is not None else None)
            if not title or now_kop is None:
                continue
            image = None
            img = box.css_first("img.ia--real-image")
            if img is not None:
                s = img.attributes.get("src") or ""
                if s.startswith("http"):
                    image = s
                elif s.startswith("/"):
                    image = BASE + s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=None,
                               image_url=image))
        return out
