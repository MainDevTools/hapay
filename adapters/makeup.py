"""Адаптер MakeUp (makeup.com.ua) — лістинг категорії. Тир D: CSS BEM-токени. РЕЖИМ: render.

Розвідка 2026-07-23. Дрогерія-гігант із «поличкою техніки» — ПЕРШИЙ спеціаліст
розділу «Краса і догляд»: фени, стайлери+фени-щітки (укладка), електричні зубні
щітки, епілятори — 4/6 слагів розділу (електробритв/тримерів як приладів нема:
їхні «бритви» — ручні станки-дрогерія, не реєструємо).

⚠ ЧОМУ РЕЖИМ RENDER: категорії за AWS WAF (кука aws-waf-token) — без неї
urllib отримує ПОРОЖНЮ відповідь (0KB, 3/3 спроб). З токеном браузерної сесії
SSR віддає повний лістинг (1154KB, ціни в HTML). WebView проходить WAF-челендж
природно. Розвідку й касету знято крізь токен сесії.

Розмітка: класи виду «ProductCard__title shop_1abc_xyz» — хеш-суфікс міняється
білдом, але ПЕРШИЙ токен (BEM-префікс) стабільний і селектиться як клас:

    <div class="ProductCard__cardContainer shop_…">
      <a class="ProductCard__link shop_…" href="/ua/product/686339/">
        …<div class="ProductCard__title shop_…">Фен для волосся</div>
        <div class="ProductCard__subTitle shop_…">Philips Essential Care BHC010/10</div>…
      <div class="Price__price shop_…">
        <span class="Price__priceOld shop_…">2630 ₴</span>      ← лише на акційних
        <span class="Price__priceCurrent shop_…">2235 ₴</span>

Нюанси:
- НАЗВА = title («Фен для волосся» — тип) + subTitle («Philips … BHC010/10» —
  бренд+модель, там живе MPN). Клеїмо через пробіл: без subTitle матчер сліпий,
  без title губиться тип товару.
- Пагінація КЛІЄНТСЬКА: ?page=2, /page-2/, /2/ — усі віддають ті самі 36 карток
  (звірено SKU — урок Eldorado) → pages=1, top-36/категорію.
- href відносні /ua/product/NNNNNN/ — клеїмо до BASE.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://makeup.com.ua"


class MakeupAdapter:
    source_name = "MakeUp"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for box in tree.css(".ProductCard__cardContainer"):
            a = box.css_first("a.ProductCard__link")
            href = (a.attributes.get("href") or "") if a is not None else ""
            if "/product/" not in href:
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            t1 = box.css_first(".ProductCard__title")
            t2 = box.css_first(".ProductCard__subTitle")
            title = " ".join(x.text().strip() for x in (t1, t2)
                             if x is not None and x.text().strip())
            cur = box.css_first(".Price__priceCurrent")
            old = box.css_first(".Price__priceOld")
            now_kop = parse_price_to_kop(cur.text() if cur is not None else None)
            old_kop = parse_price_to_kop(old.text() if old is not None else None)
            if not title or now_kop is None:
                continue
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None
            image = None
            img = box.css_first("img")
            if img is not None:
                s = img.attributes.get("src") or img.attributes.get("data-src") or ""
                if s.startswith("http"):
                    image = s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=old_kop,
                               image_url=image))
        return out
