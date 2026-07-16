"""Екстрактор Pethouse (акції-лістинг) — розмітка після редизайну 2026-07 (§3.3).

Структура: картка товару = `div.group.relative.grid` з `<a href="/ua/shop/..."><img alt=назва>`,
всередині — кілька ВАРІАНТ-рядків `div.py-4` (фасування), кожен зі своєю ціною:
  unit `грн/кг` · варіант-чип (`.bg-main-bg`, «400 грамів») · стара `.line-through`
  · знижка `.bg-red` («-15%») · поточна `.price-field` («212,50₴»).
Один RawItem на ВАРІАНТ; external_ref = url#v=<варіант> (§4.8/GAP15).

Стійкість: селектори прив'язані до семантичних класів (`price-field`, `line-through`,
`bg-main-bg`, `bg-red`), не до повного Tailwind-рядка — дрібні зміни утиліт не ламають.
"""
from __future__ import annotations
import re
from selectolax.parser import HTMLParser
from .base import RawItem, parse_price_to_kop, canon_ref, slugify


class PethouseAdapter:
    source_name = "Pethouse"

    def extract(self, html: str) -> list[RawItem]:
        tree = HTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css("div.group.relative.grid"):
            link = card.css_first('a[href*="/ua/shop/"]')
            if link is None:
                continue
            url = link.attributes.get("href") or ""
            if not url:
                continue
            img = card.css_first("img")
            title = ((img.attributes.get("alt") if img else "") or "").strip()
            image_url = (img.attributes.get("src") if img else None) or None

            rows = card.css("div.py-4")
            if not rows:                       # запобіжник, якщо обгортка варіанта зміниться
                rows = [card]
            for row in rows:
                pf = row.css_first("div.price-field")
                if pf is None:
                    continue
                now = parse_price_to_kop(pf.text())
                if now is None:                # парс-помилка ціни → пропуск (не 0 в історію, guardrail)
                    continue
                lt = row.css_first(".line-through")
                old = parse_price_to_kop(lt.text()) if lt is not None else None

                chip = row.css_first("div.bg-main-bg")
                variant = (chip.text().strip() if chip is not None else "") or ""

                mu = re.search(r"\d[\d\s.,]*грн\s*/\s*кг", row.text() or "")
                unit_text = re.sub(r"\s+", " ", mu.group(0)).strip() if mu else None

                disc = row.css_first("div.bg-red")
                discount_pct = None
                if disc is not None:
                    m = re.search(r"(\d{1,2})", disc.text() or "")
                    if m:
                        discount_pct = int(m.group(1))

                low = (row.text() or "").lower()
                in_stock = not ("немає" in low or "нет в наличии" in low)

                ext = canon_ref(url) + (("#v=" + slugify(variant)) if variant else "")
                if ext in seen:
                    continue
                seen.add(ext)
                items.append(RawItem(
                    external_ref=ext, url=url,
                    title=(f"{title} — {variant}" if variant else title),
                    price_now_kop=now, price_old_kop=old, in_stock=in_stock,
                    unit_text=unit_text, variant_note=variant or None,
                    image_url=image_url, discount_pct=discount_pct,
                ))
        return items
