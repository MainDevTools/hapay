"""Разовий перерахунок `store_product.mpn` наявним товарам за поточним матчером.

Навіщо окремий скрипт, а не міграція: логіка витягання артикула — регулярні вирази
в `matching.extract_mpn`, у SQL її не повторити чесно (а дублювати — значить розійтись).

Коли потрібен: після зміни правил матчингу. Інакше наявні рядки дістануть новий mpn
лише при наступному зборі того ж лістинга (repeat ~720 хв), тобто до півдоби товари
лежатимуть незгрупованими. Скрипт це прискорює.

Безпечно: `store_product` і так мутабельний — збір перезаписує mpn при кожному upsert
(ON CONFLICT DO UPDATE). Ідемпотентний: повторний запуск нічого не змінює.
Історію цін (append-only `price_snapshot`) НЕ чіпає.

Запуск на сервері:
    DATABASE_URL=... /opt/hapay/venv/bin/python -m scripts.backfill_mpn --dry-run
    DATABASE_URL=... /opt/hapay/venv/bin/python -m scripts.backfill_mpn
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg                                    # noqa: E402
from matching import extract_mpn                  # noqa: E402


def main() -> int:
    dry = "--dry-run" in sys.argv
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL не задано", file=sys.stderr)
        return 1

    with psycopg.connect(url, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT store_product_id, title, mpn FROM store_product").fetchall()

        changes = [(spid, extract_mpn(title), old)
                   for spid, title, old in rows]
        changes = [(spid, new, old) for spid, new, old in changes if new != old]

        added = sum(1 for _, new, old in changes if old is None and new is not None)
        removed = sum(1 for _, new, old in changes if new is None and old is not None)
        altered = len(changes) - added - removed

        print(f"товарів у базі: {len(rows)}")
        print(f"зміниться:      {len(changes)}  (+{added} нових, ~{altered} змінених, "
              f"-{removed} знятих)")
        for spid, new, old in changes[:5]:
            print(f"   #{spid}: {old!r} → {new!r}")

        if dry:
            print("\n[--dry-run] нічого не записано")
            return 0
        if not changes:
            print("нема чого міняти")
            return 0

        with conn.cursor() as cur:
            cur.executemany("UPDATE store_product SET mpn = %s WHERE store_product_id = %s",
                            [(new, spid) for spid, new, _ in changes])

        grouped = conn.execute(
            "SELECT count(*) FROM (SELECT mpn FROM store_product WHERE mpn IS NOT NULL "
            "GROUP BY mpn HAVING count(DISTINCT source_id) > 1) g").fetchone()[0]
        print(f"\nоновлено: {len(changes)}")
        print(f"крос-крамничних груп тепер: {grouped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
