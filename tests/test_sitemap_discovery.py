"""Тест sitemap-відкриття (T20) — БЕЗ БД, на касеті з реальних записів sitemap add.ua.

Sitemap — правово найчистіший канал відкриття (вет 2026-07-22): крамниця сама публікує
його в robots.txt для краулерів. Сервер фільтрує include_re → картки в чергу.

Головні пастки, які стережемо (обидві — реальні, не вигадані):
  1. «ПОРО́ШОК»: перший замір фільтра `rosh` зловив 1003 «La Roche», з яких 817 —
     porosh-ok. Патерн `la-roche` мусить НЕ матчити амбулаторний порошок.
  2. ЧУЖИЙ ХОСТ: sitemap — зовнішні дані; URL не з хостів джерела (навмисний чи битий)
     не має збити збір на сторонній сайт (та сама політика, що у validate_item).

Запуск:  python tests/test_sitemap_discovery.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.ingest import HTML_SOURCES, sitemap_locs, ingest_html, collect_plan   # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")
HOSTS = ("add.ua",)


def _cas():
    with open(os.path.join(CAS, "addua_sitemap.xml"), encoding="utf-8") as f:
        return f.read()


def test_filter_matches_la_roche_not_poroshok():
    """`la-roche` бере 2 справжні товари; porosh-ok і сторонній alaktin — НІ."""
    locs = sitemap_locs(_cas(), r"la-roche", HOSTS, cap=100)
    assert len(locs) == 2, locs
    assert all("la-roche" in u for u in locs), locs
    assert not any("poroshok" in u for u in locs), "porosh-ok приліз — патерн зіпсуто"


def test_foreign_host_dropped():
    """evil.example.com має la-roche у слазі — але чужий хост відкидається."""
    locs = sitemap_locs(_cas(), r"la-roche", HOSTS, cap=100)
    assert not any("evil" in u for u in locs), locs


def test_dedup_within_sitemap():
    """Той самий URL двічі в sitemap → один раз у результаті."""
    locs = sitemap_locs(_cas(), r"la-roche", HOSTS, cap=100)
    assert len(locs) == len(set(locs)), locs


def test_cap_limits_output():
    locs = sitemap_locs(_cas(), None, HOSTS, cap=1)
    assert len(locs) == 1, locs


def test_no_include_re_returns_all_on_host():
    """Без include_re — всі URL хоста (4 унікальні add.ua; чужий — геть)."""
    locs = sitemap_locs(_cas(), None, HOSTS, cap=100)
    assert len(locs) == 4, locs


def test_ingest_html_routes_sitemap_url():
    """ingest_html із sitemap-URL AddUa → kind='sitemap' + discovered (2 La Roche).
    conn=None доводить, що маршрут НЕ чіпає БД (як hub-фаза) — чисте відкриття."""
    sm_url = HTML_SOURCES["AddUa"]["sitemap"]["url"]
    result = ingest_html(None, "AddUa", sm_url, _cas())
    assert result["kind"] == "sitemap", result
    assert len(result["discovered"]) == 2, result["discovered"]
    assert all(u.startswith("https://www.add.ua/") for u in result["discovered"])


def test_collect_plan_has_sitemap_as_fetch():
    """У плані збору sitemap AddUa — mode='fetch', хоч крамниця render: XML тягнеться
    plain GET-ом (WebView загорнув би його у свій viewer і спотворив)."""
    plan = collect_plan()
    entries = [t for t in plan if t["source"] == "AddUa" and t["kind"] == "sitemap"]
    assert len(entries) == 1, entries
    assert entries[0]["mode"] == "fetch", entries[0]
    # render-листинг AddUa із плану зник — відкриття тепер через sitemap
    assert not [t for t in plan if t["source"] == "AddUa" and t["kind"] == "page"], \
        "листинг-задачі AddUa мали зникнути з плану (відкриття через sitemap)"


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
