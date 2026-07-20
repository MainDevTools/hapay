"""Канонічна таксономія зоо-вертикалі + категоризація товару за URL (§2.6).

Плоский набір (без ієрархії — простіше для UI); категорія виводиться з шляху
товарного URL (обидві крамниці мають тварину+тип у шляху). Невпізнане → 'inshe'.

Для електроніки базова категорія береться з ЛІСТИНГА, який зібрали (0007), а
`refine_category` уточнює її за НАЗВОЮ: деякі лістинги — широкі департаменти
(Brain «Смартфони та зв'язок») і містять кабелі/навушники впереміш із телефонами.
"""
from __future__ import annotations

import re

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


# ── уточнення категорії за назвою (для пристроєвих лістингів) ──────────────────────
# Пристроєві категорії, у які просочуються аксесуари (широкі департаменти крамниць).
_DEVICE_CATS = {"smartfony", "noutbuky", "planshety", "tv"}

# Сильні сигнали, яких у назві САМОГО пристрою практично не буває (кабель/навушники…).
# Тримаємо консервативно й у синхроні з бекфілом 0009 (ті самі слова як ILIKE).
_AUDIO_RE = re.compile(r"навушник|гарнітур|airpods|earbuds", re.I)
_ACC_RE = re.compile(
    r"кабель|power\s*bank|павербанк|повербанк|зарядний пристрій|зовнішній акумулятор|"
    r"чохол|захисне скло|захисна плівк|автотримач|стилус", re.I)


def refine_category(base_slug: str, title: str) -> str:
    """Уточнює категорію-з-лістинга за назвою товару. Лише для пристроєвих лістингів:
    кабель/зарядка/чохол → 'aksesuary', навушники/гарнітура → 'audio'. Інакше — база.

    Високоточно: спрацьовує тільки на словах, яких у назві телефона/ноутбука не буває,
    тож реальні пристрої не чіпає. Зоо та інші не-пристроєві бази лишає незмінними.
    """
    if base_slug not in _DEVICE_CATS:
        return base_slug
    t = title or ""
    if _AUDIO_RE.search(t):
        return "audio"
    if _ACC_RE.search(t):
        return "aksesuary"
    return base_slug


# ── метадані для сітки-каталогу (E-Katalog-стиль, §17): розділ + іконка ────────────
# Розділ групує категорії на головній; іконка — емодзі для плитки MAUI. Категорія без
# запису → розділ «Інше». Сервер — авторитет: додати категорію = дописати сюди рядок.
CATEGORY_UI = {
    "smartfony":       ("Електроніка", "📱"),
    "noutbuky":        ("Електроніка", "💻"),
    "planshety":       ("Електроніка", "📲"),
    "tv":              ("Електроніка", "📺"),
    "audio":           ("Електроніка", "🎧"),
    "smart-hodynnyky": ("Електроніка", "⌚"),
    "foto":            ("Електроніка", "📷"),
    "pobut-tehnika":   ("Електроніка", "🧺"),
    "konsoli":         ("Електроніка", "🎮"),
    "aksesuary":       ("Електроніка", "🔌"),
    "koty-suhyi-korm": ("Зоотовари", "🐱"),
    "psy-suhyi-korm":  ("Зоотовари", "🐶"),
    "koty-konservy":   ("Зоотовари", "🥫"),
    "psy-konservy":    ("Зоотовари", "🥫"),
    "koty-shampuni":   ("Зоотовари", "🧴"),
    "psy-shampuni":    ("Зоотовари", "🧴"),
    "amunitsiya":      ("Зоотовари", "🦴"),
}
_DEFAULT_UI = ("Інше", "📦")
# порядок розділів на головній (менше = вище)
SECTION_ORDER = {"Електроніка": 1, "Зоотовари": 2, "Інше": 9}


def category_ui(slug: str) -> tuple[str, str]:
    """(розділ, іконка) для категорії; невідома → ('Інше', '📦')."""
    return CATEGORY_UI.get(slug, _DEFAULT_UI)
