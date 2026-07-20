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
