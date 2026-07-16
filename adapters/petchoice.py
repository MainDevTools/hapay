"""Екстрактор PetChoice (miniShop2/MODX) — акції-лістинг (§3.3, тир A SSR).

Структура: картка = `form.ms2_form` (+ `input[product_id]`), назва `.product-item-title a`,
фото `/assets/...`, знижка `.discount-lbl`. Мультиваріант: `ul.product-list > li.product-option`,
кожен: `<span>`-розмір, `data-product-key` (стабільний ключ), `button[data-product-price="1020.00"]`
(чиста поточна ціна), стара — `.product-price-old` РОЗБИТА грн+коп (`<div>1360<div class=small>00</div></div>`).
Один RawItem на варіант; external_ref = url#v=<data-product-key> (§4.8).
"""
from __future__ import annotations
import re
from urllib.parse import urljoin
from selectolax.parser import HTMLParser
from .base import RawItem, parse_price_to_kop, canon_ref, slugify

BASE = "https://petchoice.ua/"


def _split_price_kop(node) -> int | None:
    """miniShop2-формат: грн (прямий текст) + коп (дочірній `.small`). '1360'+'00' → 136000."""
    if node is None:
        return None
    grn = re.sub(r"\D", "", node.text(deep=False) or "")
    if not grn:
        return None
    small = node.css_first(".small")
    kop = (re.sub(r"\D", "", small.text() or "") if small is not None else "") or "0"
    return int(grn) * 100 + int(kop[:2])


class PetChoiceAdapter:
    source_name = "PetChoice"

    def extract(self, html: str) -> list[RawItem]:
        tree = HTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for form in tree.css("form.ms2_form"):
            title_a = form.css_first(".product-item-title a") or form.css_first("a[href]")
            if title_a is None:
                continue
            title = (title_a.text() or "").strip()
            url = urljoin(BASE, (title_a.attributes.get("href") or "").strip())
            img = form.css_first("img")
            src = (img.attributes.get("src") or img.attributes.get("data-src")) if img is not None else None
            image_url = urljoin(BASE, src) if src else None

            variants = form.css("li.product-option") or [form]
            for li in variants:
                btn = li.css_first("button[data-product-price]")
                now = None
                if btn is not None:
                    now = parse_price_to_kop(btn.attributes.get("data-product-price"))
                if now is None:                                   # фолбек на розбиту .product-price
                    now = _split_price_kop(li.css_first(".product-price"))
                if now is None:
                    continue
                old = _split_price_kop(li.css_first(".product-price-old"))

                size = (btn.attributes.get("data-size").strip() if btn is not None
                        and btn.attributes.get("data-size") else "")
                if not size:
                    span = li.css_first("span")
                    size = (span.text() or "").strip() if span is not None else ""
                key = li.attributes.get("data-product-key") or slugify(size)

                low = (li.text() or "").lower()
                in_stock = not ("закончил" in low or "закінчил" in low or "немає в наявності" in low)

                ext = canon_ref(url) + (f"#v={slugify(size)}" if size else f"#k={key}")
                if ext in seen:
                    continue
                seen.add(ext)
                items.append(RawItem(
                    external_ref=ext, url=url,
                    title=(f"{title} — {size}" if size else title),
                    price_now_kop=now, price_old_kop=old, in_stock=in_stock,
                    variant_note=size or None, image_url=image_url,
                ))
        return items
