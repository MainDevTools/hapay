"""Дерево Меркла над спостереженнями доби (S31).

Навіщо саме дерево, а не просто хеш усіх рядків. Хеш доводить цілісність лише тому,
хто має ВСІ рядки доби. Дерево дає **доказ на один запис**: людина, яка дивиться на
одну ціну в історії товару, може перевірити саме її проти опублікованого кореня —
не отримуючи від нас решти бази й не вірячи нам на слово.

Конструкція навмисно найпростіша з можливих, щоб її можна було відтворити чужим
скриптом за десять рядків:

  лист   = sha256("<store_product_id>|<price_now>|<price_old>|<in_stock>|<seen_at>")
  вузол  = sha256(лівий_hex + правий_hex)          ← конкатенація ШІСТНАДЦЯТКОВИХ рядків
  непарний останній вузол дублюється сам із собою
  корінь = вузол верхнього рівня; порожня доба → корінь порожнього рядка

⚠ Формат листа — це ПУБЛІЧНИЙ КОНТРАКТ. Змінити його — зламати всі попередні докази,
тож будь-яка зміна тут вимагає нової версії формату, а не правки на місці.
"""
from __future__ import annotations

import hashlib

LEAF_VERSION = 1


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def leaf(store_product_id: int, price_now_kop: int, price_old_kop: int | None,
         in_stock: bool, seen_at) -> str:
    """Канонічний лист. `seen_at` — ISO-8601 з таймзоною, як його віддає Postgres.

    Порожня стара ціна кодується порожнім рядком, а не «None»: рядок «None» був би
    артефактом мови, а формат мусить бути мовно-нейтральним."""
    old = "" if price_old_kop is None else str(price_old_kop)
    ts = seen_at if isinstance(seen_at, str) else seen_at.isoformat()
    return _h(f"{store_product_id}|{price_now_kop}|{old}|{'1' if in_stock else '0'}|{ts}")


def root(leaves: list[str]) -> str:
    """Корінь дерева. Порожній список → хеш порожнього рядка (доба без спостережень
    теж мусить мати печатку: «нічого не було» — теж твердження)."""
    if not leaves:
        return _h("")
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])          # непарний — дублюємо сам із собою
        level = [_h(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def proof(leaves: list[str], index: int) -> list[dict]:
    """Шлях доказу для листа `index`: список {side, hash} від низу до кореня.

    `side` каже, з якого боку приклеїти сусіда — без цього перевіряльник не знає
    порядку конкатенації й отримає інший хеш."""
    if not leaves or not (0 <= index < len(leaves)):
        return []
    path, level, idx = [], list(leaves), index
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = idx + 1 if idx % 2 == 0 else idx - 1
        path.append({"side": "right" if idx % 2 == 0 else "left", "hash": level[sibling]})
        level = [_h(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return path


def verify(leaf_hash: str, path: list[dict], expected_root: str) -> bool:
    """Перевірка доказу. Саме цю функцію може написати сторонній за десять рядків —
    і саме тому конструкція проста."""
    cur = leaf_hash
    for step in path:
        cur = _h(cur + step["hash"]) if step.get("side") == "right" else _h(step["hash"] + cur)
    return cur == expected_root


def chain(prev_chain: str | None, merkle_root: str) -> str:
    """Ланцюжок діб: підміна будь-якої давньої доби ламає ВСІ наступні ланки."""
    return _h((prev_chain or "") + merkle_root)
