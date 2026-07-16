"""Канонічна таксономія зоо-вертикалі + категоризація товару за URL (§2.6).

Плоский набір (без ієрархії — простіше для UI); категорія виводиться з шляху
товарного URL (обидві крамниці мають тварину+тип у шляху). Невпізнане → 'inshe'.
"""
from __future__ import annotations

# (slug, назва) — сідяться міграцією 0002_taxonomy.sql
SEED_CATEGORIES = [
    ("koty-suhyi-korm", "Коти · Сухий корм"),
    ("psy-suhyi-korm",  "Пси · Сухий корм"),
    ("koty-konservy",   "Коти · Консерви"),
    ("psy-konservy",    "Пси · Консерви"),
    ("koty-shampuni",   "Коти · Шампуні та догляд"),
    ("psy-shampuni",    "Пси · Шампуні та догляд"),
    ("amunitsiya",      "Амуніція (нашийники, повідці)"),
    ("inshe",           "Інше"),
]

_ANIMAL = {
    "koty": ("koshkam", "koshk", "/koty", "koty", "koshek", "/cat", "cats"),
    "psy":  ("sobakam", "sobak", "/psy", "/psam", "/dog", "dogs"),
}
# амуніція — не тваринно-специфічна категорія
_AMMO = ("oshejnik", "oshejniki", "amunic", "povid", "nashijnyk", "nashyjnyk", "collar", "leash")


def categorize(url: str) -> str:
    low = (url or "").lower()
    if any(k in low for k in _AMMO):
        return "amunitsiya"
    animal = next((a for a, keys in _ANIMAL.items() if any(k in low for k in keys)), None)
    if "shampun" in low or "shampoo" in low:
        typ = "shampuni"
    elif any(k in low for k in ("konserv", "vologij", "vologi", "vlazh", "vlazhn", "wet-food")):
        typ = "konservy"
    elif any(k in low for k in ("suhoi-korm", "suxoj-korm", "suhij", "suhyi", "suhoy", "dry-food", "suxij")):
        typ = "suhyi-korm"
    else:
        typ = None
    if animal and typ:
        return f"{animal}-{typ}"
    return "inshe"
