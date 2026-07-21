"""Адаптер Венкона (vencon.ua) — лістинг категорії. Тир A: SSR plain-GET.

Розвідка 2026-07-21. Як і Епіцентр, крамниця розмічає картки schema.org, тож
екстракція йде першим тиром порядку (§8.4) — мікроданими, а не класами.

    <article itemprop="item" itemscope itemtype="https://schema.org/Product">
      <div class="article-number"> Код: 286364 </div>
      <a class="product-title" href="/products/bosch-bgs05a220"
         title="Пылесос Bosch BGS05A220" itemprop="url">
        <span itemprop="name"><span class="product-type">Пылесос </span><span>Bosch BGS05A220</span></span>
      <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
        <div class="old-price">8 499 грн</div>
        <span class="actual">7 399 <span class="currency">грн</span></span>
        <meta itemprop="price" content="7399">
        <meta itemprop="availability" content="https://schema.org/InStock">

⚠ ТРИ ПАСТКИ, кожна тиха (нічого не падає, просто дані виходять кривими):

1. `itemprop="name"` у картці трапляється ВІСІМ разів: назва товару, напис на кнопці
   «Купить» і підпис КОЖНОЇ характеристики (`Мощность, Вт`, `Уровень шума, дБ`…).
   Селектор `[itemprop=name]` без прив'язки до посилання витягує сміття — я на цьому
   вже спіймався при розвідці й отримав «18% товарів з артикулом» замість 70%.

2. Текст назви ЗЛИПЛИЙ: `<span>Пылесос </span><span>Bosch BGS05A220</span>` після
   `.text()` дає «ПылесосBosch BGS05A220». Тому назву беремо з атрибута `title`
   самого посилання — там вона з нормальними пробілами.

3. `priceValidUntil` тут стоїть на рік уперед (2027-07-21) і однаковий для всіх
   товарів, тобто це не строк акції, а заглушка. У `promo_until` НЕ кладемо: інакше
   кожна позиція виглядала б як акція з дедлайном.

Стара ціна — у `.old-price` (текстом, «8 499 грн»), а не в розмітці Offer.
MPN у назві (модель без дужок) → матчинг T15.

── ЧОМУ НЕ ЛИШЕ МІКРОДАНІ ──────────────────────────────────────────────────────
Венкон розмічає schema.org НЕ ВСІ розділи. Пилососи, мікрохвильовки, мультиварки,
пральні, посудомийні, проточні водонагрівачі, витяжки й варильні поверхні —
розмічені. Кондиціонери, бойлери, блендери, сушильні, духові шафи й плити мають
ті самі картки, але БЕЗ жодного `itemprop`.

Спокуса взяти лише розмічені розділи хибна: без кондиціонерів, бойлерів і
блендерів Венкон утрачає весь сенс — саме ці полиці мають у нас лише три крамниці,
і четверта потрібна саме там.

Тому чіпляємось за спільний контейнер картки `.static-visible-container` (він
однаковий в обох розкладках, перевірено обходом дерева вгору від `a.product-title`),
а всередині беремо ціну з мікроданих КОЛИ ВОНИ Є, інакше з `.product-price .actual`.
Це свідомий спуск на нижчий тир порядку (§8.4) для частини розділів, а не замість
нього: де розмітка є, читаємо саме її.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from .base import RawItem, canon_ref, parse_price_to_kop

BASE = "https://vencon.ua"


class VenconAdapter:
    source_name = "Vencon"

    def extract(self, html: str) -> list[RawItem]:
        tree = LexborHTMLParser(html)
        items: list[RawItem] = []
        seen: set[str] = set()

        for card in tree.css(".static-visible-container"):
            a = card.css_first("a.product-title")
            if a is None:
                continue
            # title атрибута, а не text(): див. пастку 2 у шапці модуля
            title = " ".join((a.attributes.get("title") or "").split())
            if not title:
                continue

            href = (a.attributes.get("href") or "").split("?")[0].split("#")[0]
            if not href:
                continue
            url = href if href.startswith("http") else BASE + href

            # мікродані, коли є; інакше видима ціна тієї ж картки
            meta = card.css_first('meta[itemprop="price"]')
            shown = card.css_first(".product-price .actual")
            now_kop = parse_price_to_kop(
                meta.attributes.get("content") if meta is not None
                else (shown.text() if shown is not None else None))
            if now_kop is None:
                continue                      # без поточної ціни позиція нам не потрібна

            old = card.css_first(".old-price")
            old_kop = parse_price_to_kop(old.text()) if old else None
            if old_kop is not None and old_kop <= now_kop:
                old_kop = None                # «стара» не вища за поточну — не знижка

            avail = card.css_first('meta[itemprop="availability"]')
            if avail is not None:
                in_stock = "OutOfStock" not in (avail.attributes.get("content") or "")
            else:
                label = card.css_first(".availability-label")
                in_stock = "нет" not in (label.text().lower() if label else "")

            img = card.css_first("img")
            src = (img.attributes.get("src") or img.attributes.get("data-src")) if img else None
            image_url = (src if not src or src.startswith("http") else BASE + src)

            ext = canon_ref(urlsplit(url).path)   # /products/<slug> — стабільний ключ (§4.8)
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
            ))
        return items
