"""Адаптер Yabko (jabko.ua) — лістинг категорії. Тир D: CSS, семантичні класи.

Розвідка 2026-07-23. Apple-мережа (iPhone/Mac/iPad/Watch + гаджети) — сильні
крос-крамничні категорії: iPad MPN 24/24, GoPro 18/24. OpenCart-рід, SSR
plain-GET, burst 200×3, robots дозволяє (route=-сміття закрите).

    <div class="catalog-product-item">
      …<a title="Екшн-камера GoPro Hero 13 Black (CHDHX-131-RW) (Standard)"
          class="catalog-product-item--title" href="https://jabko.ua/gadzheti-…-rw">…</a>
      <div class="catalog-product-item--set hidden">
        <span class="old">432$</span>                       ← ⚠ ЦЕ НЕ СТАРА ЦІНА
        <span class="current">19 399&nbsp;<span>грн</span></span>

⚠ ГОЛОВНА ПАСТКА — ВАЛЮТА: span.old — ціна В ДОЛАРАХ (двовалютний показ Yabko),
НЕ перекреслена стара ціна. Заміряно: 24/24 old-спанів на сторінці мають «$».
Взяти її як price_old — отримати «знижку» з курсу долара. Тому old=None ЗАВЖДИ
(заявлених старих цін у лістингу крамниця не показує; per-store Omnibus-історія
накопичується з current). current — «19 399&nbsp;грн», nbsp-сутності чистяться.

Нюанси: назва — з title-атрибута лінка (текст той самий, але з хвостами
пробілів); href абсолютні; фото — перший img слайдера картки.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://jabko.ua"


class YabkoAdapter:
    source_name = "Yabko"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for box in tree.css("div.catalog-product-item"):
            a = box.css_first("a.catalog-product-item--title")
            if a is None:
                continue
            href = a.attributes.get("href") or ""
            if not href:
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            title = (a.attributes.get("title") or "").strip() or (a.text() or "").strip()
            cur = box.css_first(".catalog-product-item--set .current")
            raw = cur.text().replace(" ", " ") if cur is not None else None
            now_kop = parse_price_to_kop(raw)
            if not title or now_kop is None:
                continue
            image = None
            img = box.css_first("img")
            if img is not None:
                s = img.attributes.get("src") or img.attributes.get("data-src") or ""
                if s.startswith("http"):
                    image = s
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=None,
                               image_url=image))
        return out
