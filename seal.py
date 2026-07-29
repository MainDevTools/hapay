"""Запечатування доби: корінь Меркла + ланцюжок (S31).

Ходить раз на добу після півночі й запечатує ВСІ ще не запечатані ПОВНІ доби.
Сьогоднішню не чіпає: доба триває, і печатка на неповних даних була б хибною.

    python seal.py            # запечатати все, що дозріло
    python seal.py --dry-run  # показати, не записуючи

⚠ Ідемпотентний: доба, яка вже має печатку, пропускається. Перезапечатування —
не «оновлення», а підміна доказу, тому таблиця ще й незмінна на рівні тригера.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import merkle                          # noqa: E402
from db.pool import get_pool           # noqa: E402
from api import db as qdb              # noqa: E402


def seal_day(conn, day: str, dry_run: bool = False) -> dict:
    rows = qdb.day_rows(conn, day)
    leaves = [merkle.leaf(r["store_product_id"], r["price_now_kop"], r["price_old_kop"],
                          r["in_stock"], r["seen_at"]) for r in rows]
    root = merkle.root(leaves)
    prev = qdb.last_seal(conn)
    prev_chain = prev["chain"] if prev else None
    ch = merkle.chain(prev_chain, root)
    if not dry_run:
        qdb.insert_seal(conn, day, len(rows), root, prev_chain, ch)
        conn.commit()
    return {"day": day, "rows": len(rows), "root": root, "chain": ch}


def run(dry_run: bool = False) -> list[dict]:
    out = []
    with get_pool().connection() as conn:
        for day in qdb.unsealed_days(conn):
            out.append(seal_day(conn, day, dry_run))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Печатка доби")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    res = run(a.dry_run)
    if not res:
        print("нових повних діб немає — усе вже запечатано")
    for r in res:
        print(f"{r['day']}  спостережень {r['rows']:>6}  корінь {r['root'][:16]}…  "
              f"ланцюжок {r['chain'][:16]}…")
