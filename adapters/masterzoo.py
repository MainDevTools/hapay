"""Адаптер MasterZoo (masterzoo.ua) — лістинг категорії. Тир D: CSS. РЕЖИМ: render.

Розвідка 2026-07-23 (два заходи). Зоо-мережа №2 — розділ «Зоотовари»: корми
сухі/вологі для котів і псів + амуніція. Пагінація справжня (?page=2 → інші SKU,
звірено фактом у браузері), 60 карток/сторінку.

⚠ ЧОМУ РЕЖИМ RENDER — АНТИ-БОТ-ЧЕЛЕНДЖ ІЗ ДВОМА ЛИЧИНАМИ:
Без куки `challenge_passed` сервер віддає ЛИБО порожню відповідь (3/4 запитів),
ЛИБО staging Next.js-шелл (Tailwind-класи, S3-bucket masterzoo-staging-assets)
БЕЗ ЦІН у DOM — обидва непридатні. З пройденим челенджем (кука) приходить
класичний SSR-шаблон з цінами. WebView проходить челендж природно (виконує JS),
тому mode="render". Plain-fetch працює ЛИШЕ з живою челендж-кукою — покладатись
на неї не можна: протухає.

Розмітка класичного шаблону (семантична, знято з відрендереного DOM браузера):

    <li class="catalog-grid__item" itemscope itemtype="…/ListItem">
      <div class="catalogCard j-catalog-card">
        …
        <div class="catalogCard-title">
          <a href="/ua/catalog/koti/korm-dlya-kotv/cat-chow/…-kurytsa/"
             title="Cухий корм для котів Cat Chow Urinary 1,5 кг - курка">…</a></div>
        <div class="catalogCard-priceBox">
          <div class="catalogCard-oldPrice"> 2 837.00 грн </div>   ← лише на акційних
          <div class="catalogCard-price"> 1 999.00 грн </div></div>

Нюанси:
- Ціни «2 837.00 грн» — пробіл-тисячник + крапка-десяткова; parse_price_to_kop
  справляється (283700 коп). Кома тут НЕ вживається (на відміну від Zootovary).
- href/src ВІДНОСНІ — клеїмо до BASE. Фото: img.catalogCard-img (/content/images/…).
- Текст у .catalogCard-title a має хвости пробілів — беремо title-атрибут, fallback text.
- Матчер очікувано слабкий (описові назви кормів) → per-store Omnibus;
  крос-крамнично корми звіряються із Zootovary порційно (той самий бренд+діета+вага).
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://masterzoo.ua"


class MasterzooAdapter:
    source_name = "MasterZoo"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for box in tree.css("div.catalogCard"):
            a = box.css_first(".catalogCard-title a")
            if a is None:
                continue
            href = a.attributes.get("href") or ""
            if "/ua/catalog/" not in href:
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            title = (a.attributes.get("title") or "").strip() or (a.text() or "").strip()
            cur = box.css_first(".catalogCard-price")
            old = box.css_first(".catalogCard-oldPrice")
            now_kop = parse_price_to_kop(cur.text() if cur is not None else None)
            old_kop = parse_price_to_kop(old.text() if old is not None else None)
            if not title or now_kop is None:
                continue
            image = None
            img = box.css_first("img.catalogCard-img")
            if img is not None:
                s = img.attributes.get("src") or ""
                if s.startswith("http"):
                    image = s
                elif s.startswith("/"):
                    image = BASE + s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=old_kop,
                               image_url=image))
        return out
