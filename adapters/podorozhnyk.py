"""Адаптер Подорожника (podorozhnyk.ua) — аптечна мережа, НЕрецептурні розділи.
Тир B: JSON-стан, вбудований у SSR-сторінку (plain-GET, резидентний IP).

Перша аптека в каталозі (розвідка 2026-07-22). Взята не заради миттєвих порівнянь —
одна крамниця їх не дає, — а щоб закласти GTIN-каталог: коли додасться друга аптека,
групи «Де купити» зійдуться за штрихкодом надійно (матчер T-GTIN), чого назва не дала б.

Сторінка вбудовує повний стан у HTML: `…,"products":[{…},…],…`. Кожен товар несе все,
що нам треба, у чистому JSON — не треба ані CSS-селекторів, ані рендера:

    {"name": "Панкреатин 8000 таблетки…, 50 шт.",
     "price": {"currency":"UAH", "current": 82.6, "max": 82.6},
     "gtins": ["4820135261796","4820135260423"],
     "url": "/pankreatin-tabl-8000-50-ternofarm-ukrajina/",
     "preview": {"src": {"original": "https://i.podorozhnyk.com/products/….webp"}},
     "status": {"type": "available", "name": "Є в наявності"},
     "restrictions": {"prescription": false, …}}

Три рішення, кожне свідоме:

1. РЕЦЕПТУРНЕ ПРОПУСКАЄМО (`restrictions.prescription`). Ми зумисне збираємо лише
   нерецептурні розділи (вітаміни, дитяче, гігієна, косметика, медтовари) — там таких
   майже нема, але замір знайшов поодинокі (1 у косметиці). Це запобіжник під рішення
   власника про юр-безпечну форму: рецептурне не показуємо взагалі.

2. GTIN передаємо СИРИМИ, не чистимо тут. Валідація (контрольна цифра, відсів
   обмеженого обігу) — у pick_gtin при персисті, єдине місце правди. Дублювати її в
   адаптері означало б два джерела, що розійдуться.

3. «Стара» ціна — `price.max`, лише коли вона ВИЩА за `current` (акція). Коли рівні
   (звичайна ціна) — старої немає, інакше кожен товар виглядав би знижковим.

Беремо НАЙБІЛЬШИЙ масив `"products"` на сторінці: у стані бувають ще дрібні
(рекомендації, переглянуте), але лістинг категорії — найдовший.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from .base import RawItem, canon_ref

BASE = "https://podorozhnyk.ua"
_PRODUCTS = re.compile(r'"products":\[')


def _largest_products(html: str) -> list:
    """Усі масиви "products":[…] у стані → найдовший (лістинг категорії)."""
    best: list = []
    for m in _PRODUCTS.finditer(html):
        j = m.end() - 1          # позиція '['
        depth, k = 1, j + 1
        while depth and k < len(html):
            ch = html[k]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            k += 1
        try:
            arr = json.loads(html[j:k])
        except (ValueError, TypeError):
            continue
        if isinstance(arr, list) and len(arr) > len(best):
            best = arr
    return best


def _kop(v) -> int | None:
    """Гривні (float/int) → копійки. None, якщо не число чи не додатне."""
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
        return None
    return int(round(v * 100))


class PodorozhnykAdapter:
    source_name = "Podorozhnyk"

    def extract(self, html: str) -> list[RawItem]:
        items: list[RawItem] = []
        seen: set[str] = set()

        for p in _largest_products(html):
            if not isinstance(p, dict):
                continue
            # рецептурне не показуємо взагалі (див. рішення 1 у шапці)
            if (p.get("restrictions") or {}).get("prescription"):
                continue

            title = (p.get("name") or "").strip()
            price = p.get("price") or {}
            now_kop = _kop(price.get("current"))
            if not title or now_kop is None:
                continue                      # без назви чи ціни позиція нам не потрібна

            old_kop = _kop(price.get("max"))
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # рівна ціна — не знижка

            path = (p.get("url") or "").split("?")[0].split("#")[0]
            if not path:
                continue
            url = path if path.startswith("http") else BASE + path

            status = p.get("status") or {}
            in_stock = status.get("type") == "available"

            src = (((p.get("preview") or {}).get("src") or {}).get("original")) or None
            image_url = src if (src and src.startswith("http")) else None

            gtins = tuple(str(g) for g in (p.get("gtins") or []) if g)

            ext = canon_ref(urlsplit(url).path)   # /<slug> — стабільний ключ (§4.8)
            if ext in seen:                       # дедуп у межах сторінки (§10.1)
                continue
            seen.add(ext)

            items.append(RawItem(
                external_ref=ext,
                url=url,
                title=title,
                price_now_kop=now_kop,
                price_old_kop=old_kop,
                in_stock=in_stock,
                image_url=image_url,
                gtins=gtins,
            ))
        return items
