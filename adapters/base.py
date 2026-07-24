"""Контракт адаптера + спільні хелпери (§8.4).

RawItem — вихід екстрактора (ще НЕ рядок БД): факт ціни на момент збору.
Гроші — цілі копійки (інваріант A1); ніколи float у сховищі.
"""
from __future__ import annotations
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RawItem:
    external_ref: str          # стабільний id у межах джерела (§4.8); для варіанта — url#v=<key>
    url: str
    title: str
    price_now_kop: int         # поточна ціна, копійки
    price_old_kop: int | None  # заявлена стара, копійки (None якщо немає)
    in_stock: bool = True
    unit_text: str | None = None       # напр. "425 грн/кг" (§2.7), як подано крамницею
    variant_note: str | None = None    # напр. "4 кг" (фасування)
    image_url: str | None = None       # вказівник на фото (НЕ байти — §7.4)
    discount_pct: int | None = None    # знижка з бейджа крамниці (для sanity, не для бейджа §5)
    promo_until: str | None = None     # ISO-дата кінця дії ціни (schema.org priceValidUntil), якщо крамниця дає
    gtins: tuple[str, ...] = ()        # штрихкоди EAN/UPC із розмітки (аптеки/медтовари); ключ матчингу сильніший за назву


_SPACES = "    "   # nbsp, narrow-nbsp, thin, figure


def parse_price_to_kop(s: str | None) -> int | None:
    """UA-формат «2 000,00» / «1 700,00 ₴» / «212,50» → копійки (int). None якщо не число.

    Пробіл (у т.ч. nbsp) — роздільник тисяч; кома — десятковий (§4.8).
    «від X» тут парситься як число — обробку «від» (варіант нерозв.) робить викликач.
    """
    if not s:
        return None
    for ch in _SPACES:
        s = s.replace(ch, " ")
    s = re.sub(r"[^\d,.\s]", "", s)          # лишити цифри, кому, крапку, пробіл
    s = re.sub(r"\s+", "", s)                # прибрати роздільники тисяч
    if not s or not any(c.isdigit() for c in s):
        return None
    if "," in s:                             # кома = десятковий → крапка як тисячі геть
        s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s) * 100)
    except ValueError:
        return None


def canon_ref(url: str) -> str:
    """Канонічний ref із URL (§4.8): без query/fragment/хвостового «/», нижній регістр."""
    return url.split("?")[0].split("#")[0].rstrip("/").lower()


def slugify(text: str) -> str:
    """Стабільний ключ варіанта: «400 грамів» → «400-грамів» (кирилиця збережена)."""
    return re.sub(r"[^\w]+", "-", (text or "").strip().lower(), flags=re.UNICODE).strip("-")


# ── Характеристики з карток (S12) ─────────────────────────────────────────────────
_MAX_ATTR_NAME = 120
_MAX_ATTR_VALUE = 300   # довше — майже напевно опис-текст, а не «пара назва-значення»
_MAX_ATTRS = 80


def clean_attrs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Сирі пари зі спец-таблиці → чисті факти (інваріант B5): нормалізований пробіл,
    ліміти довжини, дедуп назв (перша перемагає — мобільний дубль блока нижче в DOM).

    ЗАДОВГЕ ЗНАЧЕННЯ ВІДКИДАЄТЬСЯ ЦІЛКОМ, не обрізається: обрізаний опис — це все ще
    шматок опису, а описи не зберігаємо ані байта (розширення B5, оператор 2026-07-24).
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, value in pairs:
        name = re.sub(r"\s+", " ", (name or "").strip())
        value = re.sub(r"\s+", " ", (value or "").strip())
        if not (2 <= len(name) <= _MAX_ATTR_NAME):
            continue
        if not (1 <= len(value) <= _MAX_ATTR_VALUE):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((name, value))
        if len(out) >= _MAX_ATTRS:
            break
    return out
