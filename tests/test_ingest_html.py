"""Тести html-ingest — СЕРВЕР парсить переслане застосунком HTML (S11 етап 3).

Чисті (без БД): двофазний discover з хабу, валідація джерела/URL/схеми/розміру, план
збору. Персист-шлях (extract → БД → видно в /discounts) перевіряє живий test_api.

Головне: застосунок = «тупий фетчер». Він НЕ вирішує, що джерело валідне, і НЕ парсить —
сервер лишається авторитетом і над списком крамниць, і над екстракцією.

Запуск:  python tests/test_ingest_html.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import ingest as ing          # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")
HUB = "https://allo.ua/ua/events-and-discounts/"


def _read(name):
    with open(os.path.join(CAS, name), encoding="utf-8") as f:
        return f.read()


def _raises(fn, needle):
    try:
        fn()
    except ValueError as e:
        assert needle in str(e), f"очікував {needle!r} у {e!r}"
        return
    assert False, f"мало кинути ValueError із {needle!r}"


# ── план збору: сервер — авторитет над списком ────────────────────────────────────

def test_plan_lists_allo_hub():
    plan = ing.collect_plan()
    assert any(t["source"] == "Allo" and t["url"] == HUB and t["kind"] == "hub" for t in plan), plan


def test_plan_lists_foxtrot_and_moyo_pages():
    """Foxtrot/Moyo — прямі лістинги (kind=page), без хаба; на своїх доменах."""
    plan = ing.collect_plan()
    fox = [t for t in plan if t["source"] == "Foxtrot"]
    moyo = [t for t in plan if t["source"] == "Moyo"]
    assert fox and all(t["kind"] == "page" and "foxtrot.com.ua" in t["url"] for t in fox), fox
    assert moyo and all(t["kind"] == "page" and "moyo.ua" in t["url"] for t in moyo), moyo


def test_every_html_source_has_host_policy():
    """Інваріант: кожне html-джерело мусить мати host-політику в INGEST_SOURCES —
    інакше ingest_html впаде на валідації URL."""
    for name in ing.HTML_SOURCES:
        assert name in ing.INGEST_SOURCES, name


# ── фаза 1: хаб → сервер робить discover() ────────────────────────────────────────

def test_hub_html_returns_discovered_landings():
    r = ing.ingest_html(None, "Allo", HUB, _read("allo_hub.html"))
    assert r["kind"] == "hub" and r["accepted"] == 0, r
    assert len(r["discovered"]) == 9, r["discovered"]
    assert all(u.startswith("https://allo.ua/ua/events-and-discounts/") and u.endswith("-action/")
               for u in r["discovered"])


def test_discovered_landings_stay_on_store_domain():
    """Лендинги мусять лишатись на allo.ua — сервер не може збити застосунок на чужий хост."""
    r = ing.ingest_html(None, "Allo", HUB, _read("allo_hub.html"))
    assert all(u.startswith("https://allo.ua/") for u in r["discovered"]), r["discovered"]


# ── валідація: застосунок не може «вигадати» джерело чи підсунути чужий/битий вхід ─

def test_unknown_source_rejected():
    _raises(lambda: ing.ingest_html(None, "Хакер", HUB, "<html></html>"), "html-джерело")


def test_url_must_be_on_store_domain():
    _raises(lambda: ing.ingest_html(None, "Allo", "https://evil.example.com/x", "<html></html>"),
            "домені")


def test_url_must_be_https():
    _raises(lambda: ing.ingest_html(None, "Allo", "http://allo.ua/ua/events-and-discounts/",
                                    "<html></html>"), "https")


def test_empty_html_rejected():
    _raises(lambda: ing.ingest_html(None, "Allo", HUB, "   "), "порожн")


def test_oversized_html_rejected():
    big = "<html>" + "x" * (ing._MAX_HTML + 1)
    _raises(lambda: ing.ingest_html(None, "Allo", HUB, big), "завеликий")


# ── пагінація (розвідка 2026-07-20) ──────────────────────────────────────────

def test_pagination_expands_and_inherits_category():
    """Сторінки 2..N будуються за схемою крамниці й УСПАДКОВУЮТЬ категорію першої —
    інакше товари з 2-ї сторінки тихо падали б у «Інше»."""
    listings = ing.source_listings(ing.HTML_SOURCES["Rozetka"])
    tv = [u for u, c, _p in listings if c == "tv"]
    assert tv[0] == "https://rozetka.com.ua/ua/all-tv/c80037/"
    assert "https://rozetka.com.ua/ua/all-tv/c80037/page=2/" in tv
    assert len(tv) == ing.HTML_SOURCES["Rozetka"]["pages"], tv
    # звіряємось із ТАКСОНОМІЄЮ, а не з переліком у тесті: інакше кожна нова
    # категорія валить перевірку, яка до неї стосунку не має (так і сталось,
    # коли додали планшети й навушники)
    from taxonomy import CATEGORY_UI
    assert all(c in CATEGORY_UI for _u, c, _p in listings), listings


def test_pagination_scheme_is_per_store():
    """Схеми різні (?page= / ?p= / page=N/) — беруться з конфігу крамниці, не вгадуються."""
    comfy = [u for u, c, _p in ing.source_listings(ing.HTML_SOURCES["Comfy"]) if c == "smartfony"]
    assert "https://comfy.ua/smartfon/?p=2" in comfy


def test_source_without_pagination_stays_single_page():
    """Eldorado — пагінація клієнтська: пряме завантаження page=N/ віддає ПЕРШУ сторінку
    (звірено за SKU), тому в нього рівно по одному лістингу на категорію."""
    cfg = ing.HTML_SOURCES["Eldorado"]
    listings = ing.source_listings(cfg)
    # суть перевірки — «жодного розгортання сторінок», а не «рівно 3 лістинги»:
    # інакше кожна нова категорія валить тест, який до неї стосунку не має
    assert len(listings) == len(cfg["urls"]), listings
    assert all(p == 1 for _u, _c, p in listings), listings


def test_per_url_depth_overrides_source_depth():
    """У Brain адреси `/ukr/category/…` пагінуються, а старий департамент
    `Smartfoni_zvyazok-c297` — ні. Тому глибина задається поштучно."""
    listings = ing.source_listings(ing.HTML_SOURCES["Brain"])
    smart = [u for u, c, _p in listings if c == "smartfony"]
    tv = [u for u, c, _p in listings if c == "tv"]
    assert len(smart) == 1, smart                     # департамент — без сторінок
    assert len(tv) == ing.HTML_SOURCES["Brain"]["pages"], tv
    assert "https://brain.com.ua/ukr/category/Televizory-c1098/page=2/" in tv


def test_paginated_urls_are_registered_for_category():
    """Кожна згенерована сторінка мусить бути в URL_CATEGORY — саме звідти
    `ingest_html` бере категорію для персисту."""
    for name, cfg in ing.HTML_SOURCES.items():
        for u, c, _p in ing.source_listings(cfg):
            if c:
                assert ing.URL_CATEGORY.get((name, u)) == c, (name, u)


def test_queue_load_fits_collector_capacity():
    """Конфіг не має замовляти більше запусків, ніж колектор фізично встигає.

    Черга — ресурс зі стелею: розліт 15 хв на крамницю дає ~384 запуски/добу. Якщо
    конфіг просить більше, нічого не «ламається» — задачі просто оновлюються рідше,
    ніж раз на 3 доби, і товари ТИХО зникають з каталогу як несвіжі. Мовчазна
    деградація найгірша, бо помітна аж через дні, тож ловимо її тут.

    Стеля НЕ константа — вона росте з числом крамниць, і це видно з `lease_tasks`:
    оренда бере `DISTINCT ON (source)`, тобто максимум ОДНУ задачу на крамницю за раз.
    Отже за одну оренду черга рухається щонайбільше на стільки задач, скільки в нас
    джерел. Нова крамниця додає не лише роботу, а й пропускну здатність.

    Заміряно 2026-07-21 на живому колекторі: 4 оренди за годину (телефон озивається
    десь раз на 17 хв), 32 сторінки за годину при 9 джерелах ≈ 3.6 сторінки на
    крамницю за годину — майже впритул до стелі розльоту (SOURCE_SPACING_MIN=15 дає
    4/год). У добу це ~85 на крамницю; беремо 60 — телефон не щогодини рівний
    (бачили години з 17 сторінками й години з нулем).

    Далі мінус ~30 на хаб-лендинги, яких у конфігу НЕМАЄ (крамниці віддають їх
    динамічно, а черга однаково їх виконує), і мінус 5% на повтори після збоїв.

    Раніше тут стояла константа 384. Вона була не просто занижена, а НЕПРАВИЛЬНА за
    будовою: не залежала від того, скільки крамниць у конфігу. Через неї я зрізав
    глибину великих категорій, вважаючи, що впираюсь у стелю.
    """
    from api.qtasks import repeat_for_page
    per_source_per_day, hub = 60, 30
    capacity = len(ing.HTML_SOURCES) * per_source_per_day
    budget = (capacity - hub) * 0.95
    runs = sum(1440.0 / repeat_for_page(p)
               for cfg in ing.HTML_SOURCES.values()
               for _u, _c, p in ing.source_listings(cfg))
    assert runs <= budget, (
        f"конфіг просить {runs:.0f} запусків/добу при бюджеті {budget:.0f} — зріж "
        f"глибину (`pages`) або прибери лістинги, перш ніж додавати нові")


def _main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v) and getattr(v, "__module__", None) == __name__]
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
