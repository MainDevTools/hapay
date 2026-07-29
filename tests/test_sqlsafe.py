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
        # ⚠ Спершу ГАСИМО пари `%%`, і лише тоді шукаємо блукаючі. Інакше в
        # екранованому відсотку помічається ДРУГИЙ символ: він же не має після себе
        # ні `s`, ні `%`. Виявлено 2026-07-29, коли `%%` уперше знадобився по-справжньому
        # (оператор схожості pg_trgm) — доти жоден запит його не містив, тож
        # запобіжник роками був зелений із хибної причини.
        probe = sql.replace("%%", "  ")
        for m in _STRAY.finditer(probe):
            around = sql[max(0, m.start() - 60):m.start() + 20].replace("\n", " ")
            raise AssertionError(f"{label}: блукаючий «%» -> ...{around}...")


def test_list_products_no_stray_percent():
    # усі гілки: з категорією, пошуком, межами ціни, лише знижки, різні сорти
    for kw in ({}, {"category": "tv"}, {"q": "acer"}, {"price_min": 1, "price_max": 9},
               {"only_discounts": True}, {"sort": "cheaper"}, {"sort": "popular"},
               {"category": "tv", "q": "a", "price_min": 1, "only_discounts": True}):
        _check(_sql_of(db.list_products, **kw), f"list_products({kw})")


def test_collect_health_no_stray_percent():
    """collect_health збирається f-рядком (умова `ok` повторюється п'ять разів), тож
    саме там найлегше занести «%» непомітно — f-рядок його не екранує."""
    from api import qtasks
    _check(_sql_of(qtasks.collect_health), "collect_health")


def test_admin_builders_no_stray_percent():
    """Адмін-панель (S16): пошук за email тягне ILIKE з `%` У ЗНАЧЕННІ (це безпечно),
    але сусідній текст запиту мусить лишатись чистим; метрики збору колись мали
    `LIKE 'fail%'` — саме той випадок, який тут ловиться."""
    for kw in ({}, {"q": "acer"}, {"role": "admin"}, {"active": False},
               {"q": "a", "role": "user", "active": True, "page": 2}):
        _check(_sql_of(db.list_users, **kw), f"list_users({kw})")
    _check(_sql_of(db.admin_metrics), "admin_metrics")
    for kw in ({}, {"action": "set_role"}, {"action": "ban", "page": 3}):
        _check(_sql_of(db.list_audit, **kw), f"list_audit({kw})")
    _check(_sql_of(db.user_detail, 1), "user_detail")


def test_new_builders_no_stray_percent():
    """⚠ Цей запобіжник ловить лише те, що в НЬОМУ перелічено. 2026-07-28 `price_drops`
    поїхав у прод із «48%» у коментарі й упав 500 — тест був зелений, бо тієї функції
    в списку не було. Кожен новий білдер SQL додавати СЮДИ, інакше запобіжник охороняє
    порожнє місце."""
    for kw in ({}, {"days": 7}, {"order": "deep"}, {"limit": 10, "offset": 10}):
        _check(_sql_of(db.price_drops, **kw), f"price_drops({kw})")
    _check(_sql_of(db.price_moves_summary), "price_moves_summary")
    _check(_sql_of(db.model_card, 1), "model_card")
    _check(_sql_of(db.store_list), "store_list")
    _check(_sql_of(db.store_meta, "comfy"), "store_meta")
    _check(_sql_of(db.category_meta, "tv"), "category_meta")
    _check(_sql_of(db.sitemap_rows), "sitemap_rows")
    _check(_sql_of(db.historical_low, 1), "historical_low")
    _check(_sql_of(db.query_watch_hits), "query_watch_hits")
    _check(_sql_of(db.refresh_models), "refresh_models")
    _check(_sql_of(db.users_for_alerts), "users_for_alerts")
    _check(_sql_of(db.spark_series, [1, 2]), "spark_series")
    # ⚠ fuzzy-гілка містить ЛІТЕРАЛЬНИЙ `%` (оператор схожості pg_trgm), який у
    # psycopg треба подвоювати. Саме той клас помилки, що зламав /api/drops 28.07,
    # лише цього разу `%` не в коментарі, а в самому операторі.
    _check(_sql_of(db.list_products, q="ноутбк", fuzzy=True), "list_products(fuzzy)")
    _check(_sql_of(db.list_products, q="ноутбк", fuzzy=True, category="tv"),
           "list_products(fuzzy+category)")


def test_other_builders_no_stray_percent():
    for fn, a, kw in ((db.list_discounts, (), {}),
                      (db.list_discounts, (), {"q": "acer", "category": "tv"}),
                      (db.product_offers, (1,), {}),
                      (db.product_history, (1,), {}),
                      (db.product_card, (1,), {}),
                      (db.categories, (), {})):
        _check(_sql_of(fn, *a, **kw), fn.__name__)


# Раннера тут не було, і в CI файл не значився — тобто запобіжник, СТВОРЕНИЙ після
# зламу CI 2026-07-21, жодного разу не виконався. Мовчазний запобіжник гірший за
# його відсутність: дає хибне відчуття захисту (виявлено 2026-07-26, S16).
def _main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)
           and getattr(v, "__module__", None) == __name__]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
