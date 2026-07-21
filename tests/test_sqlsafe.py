"""Запобіжник: у SQL не має бути «блукаючих» знаків відсотка.

psycopg сканує на плейсхолдери ВЕСЬ текст запиту — включно з коментарями. Тож
нешкідливий на вигляд коментар `-- гучне «−56%» порожнє` ламає розбір ще до того,
як запит піде в базу, і падає це аж у рантаймі:

    UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc2 ...

Саме так і сталося 2026-07-21: CI впав не на логіці, а на коментарі. Юніт-тест
дешевший за той цикл «пуш → CI → лог → здогад».

Дозволено лише `%s` (плейсхолдер) і `%%` (екранований відсоток).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import db  # noqa: E402

_STRAY = re.compile(r"%(?![s%])")


class _Cur:
    def __init__(self, box): self.box = box
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None): self.box.append(sql); return self
    def fetchall(self): return []
    def fetchone(self): return None


class _Conn:
    """Ловить SQL, не ходячи в базу."""
    def __init__(self): self.box = []
    def cursor(self, **kw): return _Cur(self.box)
    def execute(self, sql, params=None): self.box.append(sql); return _Cur(self.box)


def _sql_of(fn, *a, **kw):
    conn = _Conn()
    try:
        fn(conn, *a, **kw)
    except Exception:
        pass          # нас цікавить лише текст запиту, не його виконання
    return conn.box


def _check(sqls, label):
    for sql in sqls:
        if not isinstance(sql, str):
            continue
        for m in _STRAY.finditer(sql):
            around = sql[max(0, m.start() - 60):m.start() + 20].replace("\n", " ")
            raise AssertionError(f"{label}: блукаючий «%» → …{around}…")


def test_list_products_no_stray_percent():
    # усі гілки: з категорією, пошуком, межами ціни, лише знижки, різні сорти
    for kw in ({}, {"category": "tv"}, {"q": "acer"}, {"price_min": 1, "price_max": 9},
               {"only_discounts": True}, {"sort": "cheaper"}, {"sort": "popular"},
               {"category": "tv", "q": "a", "price_min": 1, "only_discounts": True}):
        _check(_sql_of(db.list_products, **kw), f"list_products({kw})")


def test_other_builders_no_stray_percent():
    for fn, a, kw in ((db.list_discounts, (), {}),
                      (db.list_discounts, (), {"q": "acer", "category": "tv"}),
                      (db.product_offers, (1,), {}),
                      (db.product_history, (1,), {}),
                      (db.categories, (), {})):
        _check(_sql_of(fn, *a, **kw), fn.__name__)
