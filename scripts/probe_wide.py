"""Широкий пробій крамниць-кандидатів З ПРОД-ТОЧКИ (запускати на сервері!).

Чому з сервера: Allo і Rozetka віддають 403 саме дата-центровим IP (2026-07-18),
тож доступність, виміряна з резидентної машини, для прода НЕ ДІЙСНА.

Міряє два питання разом: (1) чи пускає нас крамниця з цього IP; (2) чи віддає
сторінка знижок товари+ціни плейн-GET-ом (SSR) — тобто чи можливий адаптер класу A.

Запуск:  cd /opt/hapay/repo && /opt/hapay/venv/bin/python scripts/probe_wide.py
Ввічливо: 1-2 запити на хост, пауза між хостами.
"""
import re
import sys
import time

sys.path.insert(0, __file__.rsplit("/scripts", 1)[0] if "/" in __file__ else ".")
try:
    from collect import default_fetch
except ImportError:                      # запуск не з кореня репо
    sys.path.insert(0, ".")
    from collect import default_fetch

# (назва, URL сторінки знижок або головної, категорія)
TARGETS = [
    # зоо (наша діюча ніша)
    ("Zootovary",     "https://zootovary.com.ua/catalog/sale/", "зоо"),
    ("Petslike",      "https://petslike.net/uk/promotions", "зоо"),
    ("Zoocomplex",    "https://zoocomplex.com.ua/ua/akcii/", "зоо"),
    ("MasterZoo",     "https://masterzoo.ua/ua/akcii/", "зоо"),
    ("E-Zoo",         "https://e-zoo.com.ua/ua/actions/", "зоо"),
    # косметика/догляд
    ("EVA",           "https://eva.ua/ua/promotions/", "косметика"),
    ("Prostor",       "https://prostor.ua/ua/sale/", "косметика"),
    ("Watsons",       "https://www.watsons.ua/uk/promotions", "косметика"),
    ("MAKEUP",        "https://makeup.com.ua/ua/discounts/", "косметика"),
    # дитяче
    ("Pampik",        "https://pampik.com/ua/akcii", "дитяче"),
    ("Antoshka",      "https://antoshka.ua/ua/sale/", "дитяче"),
    # аптеки
    ("ANC",           "https://anc.ua/ua/actions", "аптека"),
    ("Podorozhnyk",   "https://podorozhnyk.ua/uk/akciyi", "аптека"),
    ("Apteka911",     "https://apteka911.ua/ua/shop/aktsii", "аптека"),
    # електроніка / техніка
    ("Brain",         "https://brain.com.ua/ukr/promotions/", "техніка"),
    ("KTC",           "https://ktc.ua/actions.html", "техніка"),
    ("Telemart",      "https://telemart.ua/ua/actions/", "техніка"),
    ("Eldorado",      "https://eldorado.ua/uk/promotions/", "техніка"),
    ("Foxtrot",       "https://www.foxtrot.com.ua/uk/actions", "техніка"),
    ("Moyo",          "https://www.moyo.ua/ua/actions", "техніка"),
    ("Can",           "https://can.ua/uk/sale/", "техніка"),
    # книги / хобі
    ("Yakaboo",       "https://www.yakaboo.ua/ua/knigi/aktsii", "книги"),
    ("BookYe",        "https://book-ye.com.ua/catalog/aktsiyni-tovary/", "книги"),
    # спорт
    ("Megasport",     "https://megasport.ua/ua/catalog/outlet/", "спорт"),
    ("Sportano",      "https://sportano.ua/promotions", "спорт"),
    ("Intertop",      "https://intertop.ua/uk/sale", "взуття/одяг"),
    ("Answear",       "https://answear.ua/ua/rasprodazha", "одяг"),
    # дім / DIY
    ("Epicentr",      "https://epicentrk.ua/ua/aktsii/", "DIY"),
    ("27ua",          "https://27.ua/ua/actions/", "DIY"),
    ("JYSK",          "https://jysk.ua/uk/aktsiyi", "меблі"),
    # маркетплейси (очікуємо фільтр, але міряємо)
    ("Rozetka",       "https://rozetka.com.ua/ua/promotions/", "маркетплейс"),
    ("Allo",          "https://allo.ua/ua/events-and-discounts/", "маркетплейс"),
    ("Prom",          "https://prom.ua/ua/", "маркетплейс"),
    ("Kasta",         "https://kasta.ua/uk/market/sale/", "маркетплейс"),
]

PRICE = re.compile(r'\d[\d\s ]{1,8}\s*(?:грн|₴)|class="[^"]*price[^"]*"[^>]*>\s*\d')
OLD = re.compile(r'old[-_]?price|line-through|<del|<s[ >]|special[-_]?price', re.I)


def main():
    print(f"{'крамниця':<13} {'кат':<11} {'HTTP':<5} {'байт':>9} {'цін':>5} {'old':>5}  вирок")
    print("-" * 78)
    ok_a = []
    for i, (name, url, cat) in enumerate(TARGETS):
        if i:
            time.sleep(2.5)
        try:
            html = default_fetch(url)
            code = "200"
        except Exception as e:
            code = re.search(r"\d{3}", str(e))
            code = code.group(0) if code else type(e).__name__[:10]
            print(f"{name:<13} {cat:<11} {code:<5} {'—':>9} {'—':>5} {'—':>5}  ✗")
            continue
        prices = len(PRICE.findall(html))
        olds = len(OLD.findall(html))
        if prices >= 20 and olds >= 5:
            verdict = "✅ КАНДИДАТ (SSR-лістинг зі знижками)"
            ok_a.append(name)
        elif prices >= 20:
            verdict = "🟡 ціни є, old-маркерів мало"
        elif prices >= 5:
            verdict = "⚠ мало цін"
        else:
            verdict = "✗ client-side/не лістинг"
        print(f"{name:<13} {cat:<11} {code:<5} {len(html):>9,} {prices:>5} {olds:>5}  {verdict}")

    print(f"\n✅ кандидатів класу A: {len(ok_a)} → {', '.join(ok_a) if ok_a else '—'}")


if __name__ == "__main__":
    main()
