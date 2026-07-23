"""Адаптер Dnipro-M (dnipro-m.ua) — лістинг категорії. Тир C/D: SSR Vue-атрибути.

Розвідка 2026-07-23. Виробник+рітейл інструменту — 10 слагів «Інструментів».
Особлива цінність: Dnipro-M продається і в Epicentr/Rozetka — коди моделей
(CD-200BC, PE-29S) дають КРОС-КРАМНИЧНИЙ матч проти загальних крамниць.

SSR віддає Vue-компоненти з даними в АТРИБУТАХ (не в DOM-тексті):

    <li class="category-products__card">
      <product-card :id="12321" code="78740000-1"
        title="Акумуляторний дриль-шуруповерт Dnipro-M CD-200BC KIT"
        link="/tovar/akumulyatornij-dril-shurupovert-cd-200bc-kit/"
        :photos="[{&quot;thumb&quot;:&quot;https:\\/\\/static.dnipro-m.ua\\/…jpg&quot;,…}]"
        price="{&quot;price_new&quot;:&quot;2997&quot;,&quot;price_old&quot;:&quot;4200&quot;}"
        :is-available="true" …>

Нюанси:
- Ціни — HTML-encoded JSON в атрибуті price: розгортаємо &quot; і json.loads.
  Значення в ГРИВНЯХ цілими рядками («2997»). ⚠ price_old заповнена ЗАВЖДИ:
  для товарів без знижки вона ДОРІВНЮЄ price_new («1590»/«1590») — брати її
  сирою означає тегувати весь асортимент фальш-знижками 0%. Лишаємо old лише
  якщо old > new (заміряно: 23/23 карток шуруповертів мають price_old, з них
  6 — рівні ціни без знижки).
- title чистий (з «Dnipro-M» усередині — лишаємо: бренд у назві допомагає матчеру).
- link відносний /tovar/…/ — клеїмо до BASE.
- Фото: перший thumb з photos-JSON (static.dnipro-m.ua) — вказівник (інваріант B).
- Пагінації в лістингах нема (бренд вузький, категорії по 5–25 товарів) → top-N.
- ⚠ НЕЗАКРИТИЙ <template> перед сіткою: за HTML5-специфікацією весь подальший
  вміст потрапляє у template-фрагмент ПОЗА головним деревом — css() бачить нуль
  карток при 23 сирих у HTML (впіймано на валідації: касета-фрагмент парсилась,
  жива сторінка — ні). Тому перед парсом перейменовуємо template-теги на
  нейтральний невідомий елемент — діти лишаються в дереві.
- Болгарки в крамниці ЛИШЕ акумуляторні (мережевих КШМ не знайдено);
  гайковерти лише пневматичні — наш слаг haikoverty (електро) НЕ реєструємо
  (subtype-mismatch, урок pnevmogaykoverty у Storgom).
"""
from __future__ import annotations

import html as _html
import json

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://dnipro-m.ua"


class DniproMAdapter:
    source_name = "DniproM"

    def extract(self, html: str) -> list[RawItem]:
        # незакритий <template> ховає сітку у фрагмент поза деревом (див. docstring)
        html = html.replace("<template", "<template-x").replace("</template", "</template-x")
        tree = LexborHTMLParser(html)
        out: list[RawItem] = []
        seen: set[str] = set()
        for pc in tree.css("product-card"):
            attrs = pc.attributes
            href = attrs.get("link") or ""
            title = (attrs.get("title") or "").strip()
            if "/tovar/" not in href or not title:
                continue
            url = href if href.startswith("http") else BASE + href
            ref = canon_ref(url)
            if ref in seen:
                continue
            now_kop = old_kop = None
            try:
                pj = json.loads(_html.unescape(attrs.get("price") or ""))
                now_kop = parse_price_to_kop(str(pj.get("price_new") or ""))
                old_raw = pj.get("price_old")
                if old_raw:
                    old_kop = parse_price_to_kop(str(old_raw))
            except (json.JSONDecodeError, AttributeError):
                pass
            if now_kop is None:
                continue
            if old_kop is not None and old_kop <= now_kop:   # рівні = «без знижки»
                old_kop = None
            image = None
            try:
                ph = json.loads(_html.unescape(attrs.get(":photos")
                                               or attrs.get("photos") or ""))
                if ph and isinstance(ph, list):
                    t = (ph[0] or {}).get("thumb") or ""
                    if t.startswith("http"):
                        image = t
            except (json.JSONDecodeError, AttributeError):
                pass
            seen.add(ref)
            out.append(RawItem(external_ref=ref, url=url, title=title,
                               price_now_kop=now_kop, price_old_kop=old_kop,
                               image_url=image))
        return out
