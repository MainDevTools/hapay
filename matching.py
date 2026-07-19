"""Крос-крамничний матчинг товарів за MPN (T15, §17.5).

Той самий фізичний товар у різних крамницях носить той самий заводський артикул
(MPN) у назві: «Samsung Galaxy A37 5G ... (SM-A376BDGGEUC)» — і в Allo, і у Foxtrot.
Витягаємо його з назви на СЕРВЕРІ при персисті → однаковий mpn = одна агрегатна
картка «Де купити».

Принцип: НЕДОзлиття безпечне (дві картки замість одної), ПЕРЕзлиття — брехня
(чужі ціни на картці). Тому правила навмисно суворі:
- повний MPN, БЕЗ обрізання регіональних суфіксів (пастка AUXUA: SM-…EUC ≠ SM-…AUXUA —
  можуть різнитись комплектацією; розвідка 2026-07-18);
- родовий токен — лише в дужках, лише латиниця/цифри, зі стоп-листом і форм-фільтрами
  проти «256GB» / «8/256GB» / EAN-штрихкодів.
"""
from __future__ import annotations

import re

# Samsung: артикул упізнаваний і поза дужками (наскрізний ключ розвідки 2026-07-18)
_SAMSUNG = re.compile(r"\bSM-[A-Z0-9]{4,15}\b")

# родовий кандидат: останній токен У ДУЖКАХ з латиниці/цифр (Apple MG6J4, MHRV4AF/A …)
_PAREN = re.compile(r"\(([A-Z0-9][A-Z0-9/\-]{3,24})\)")

# сміття, що схоже на артикул формою, але ним не є
_STOP = {"NEW", "SALE", "LTE", "NFC", "USB", "OLED", "AMOLED", "IPS",
         "HD", "FHD", "UHD", "QHD", "WIFI", "5G", "4G", "3G", "2G"}
# памʼять/характеристики: «256GB», «8/256GB», «6000MAH», «120HZ», «55W»
_SPEC = re.compile(r"[\d/]+(GB|TB|MAH|MM|CM|HZ|W|K)?")


def _plausible(tok: str) -> bool:
    """Форм-фільтр родового кандидата: ≥2 літери, ≥1 цифра, не спека, не стоп-слово."""
    if not (4 <= len(tok) <= 25) or tok in _STOP:
        return False
    letters = sum(c.isalpha() for c in tok)
    digits = sum(c.isdigit() for c in tok)
    if letters < 2 or digits < 1:
        return False          # «(PRO)» — без цифр; «(2025)» — без літер; EAN — самі цифри
    if _SPEC.fullmatch(tok):
        return False          # «256GB», «8/256GB», «6000MAH» — характеристика, не артикул
    return True


def extract_mpn(title: str | None) -> str | None:
    """MPN з назви товару або None. Детермінований, без нормалізації суфіксів."""
    if not title:
        return None
    m = _SAMSUNG.search(title)
    if m:
        return m.group(0)
    # родовий: беремо ОСТАННІЙ правдоподібний токен у дужках (артикул зазвичай наприкінці)
    for tok in reversed(_PAREN.findall(title)):
        if _plausible(tok):
            return tok
    return None
