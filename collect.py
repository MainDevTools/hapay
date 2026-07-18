#!/usr/bin/env python3
"""Колектор (Шар 1, §8.1): fetch → extract → persist → detect_pass.

Один прогін = один discovery-scan по кожному джерелу: заводить scan_run, тягне
discovery-URL(и), екстрактить RawItem, персистить у price_snapshot, наприкінці
рахує бейджі (detect_pass). Scheduled GH-workflow ганяє наживо в постійну БД;
CI-тест підставляє касету через параметр `fetch` (детерміновано, без живого HTTP).

Секрет `DATABASE_URL` — лише з env (Actions secret); ніколи в репо (git-безпека §8).
"""
from __future__ import annotations
import gzip
import os
import sys
import time
import urllib.request
import zlib

from adapters.allo import HUB as ALLO_HUB, AlloAdapter
from adapters.pethouse import PethouseAdapter
from adapters.petchoice import PetChoiceAdapter
from db import migrate
from db.store import upsert_source, persist_items, load_categories
from detection.runner import detect_pass, close_absent

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
POLITE_DELAY = 3.0          # §10.2 — пауза між запитами до одного хоста

# Реєстр джерел (discovery §3.3, тир A). Категорія — uncategorized (реальна таксономія — далі).
SOURCES = [
    {"name": "Pethouse", "base_url": "https://pethouse.ua", "platform": "custom",
     "fetch_tier": "A", "adapter": PethouseAdapter(), "category_slug": "uncategorized",
     "discount_urls": [   # per-category discovery (§3.3); підтверджено пробою 2026-07-16
         "https://pethouse.ua/ua/shop/koshkam/suhoi-korm/akcii/",
         "https://pethouse.ua/ua/shop/sobakam/suhoi-korm/akcii/",
         "https://pethouse.ua/ua/shop/koshkam/konservi/akcii/",
         "https://pethouse.ua/ua/shop/sobakam/konservi/akcii/",
         "https://pethouse.ua/ua/shop/koshkam/shampuni/akcii/",
         "https://pethouse.ua/ua/shop/sobakam/shampuni/akcii/",
     ]},
    {"name": "PetChoice", "base_url": "https://petchoice.ua", "platform": "custom",
     "fetch_tier": "A", "adapter": PetChoiceAdapter(), "category_slug": "uncategorized",
     "discount_urls": ["https://petchoice.ua/discounts"]},
    # Allo: каталог client-side, але акційні лендинги SSR (розвідка 2026-07-18).
    # hub_discovery: спершу хаб → adapter.discover() → лендинги (*-action/).
    # platform: 'custom' — власна платформа Allo (Nuxt це фронтенд, а CHECK у §6
    # дозволяє лише horoshop/opencart/woocommerce/magento/bitrix/custom)
    #
    # ⚠ enabled=False (2026-07-18): Allo віддає 403 з дата-центрових IP (Hetzner) —
    # перевірено curl-ом із сервера (403 і голим, і з браузерними заголовками), тоді
    # як із резидентних IP той самий URL — 200. Обхід проксями НЕ робимо (§7.4).
    # Адаптер робочий (golden-касети в CI). Шлях повернення — сателіт-колектор з
    # іншої точки (напр. GH Actions → POST на наш ingest-API) або зміна політики Allo.
    {"name": "Allo", "base_url": "https://allo.ua", "platform": "custom",
     "fetch_tier": "A", "adapter": AlloAdapter(), "category_slug": "uncategorized",
     "hub_discovery": True, "max_pages": 20, "enabled": False,
     "discount_urls": [ALLO_HUB]},
]


def decode_body(raw: bytes, content_encoding: str | None) -> str:
    """Розпаковує тіло за Content-Encoding. urllib цього НЕ робить сам — саме тому ми
    довго просили `identity` й качали вдев'ятеро більше байтів, ніж потрібно.

    Помилку розпаковки НЕ ковтаємо: гучний виняток спіймає `_collect_source` і покаже
    в `problems`. Тихо віддати парсеру бінарне сміття = 0 позицій зі статусом «ok» —
    цей режим відмови ми вже проходили (T13).
    """
    enc = (content_encoding or "").strip().lower()
    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        try:
            raw = zlib.decompress(raw)                     # zlib-обгортка (як велить RFC)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)    # сирий deflate — так шлють деякі сервери
    return raw.decode("utf-8", "replace")


def default_fetch(url: str) -> str:
    """GET сторінки крамниці.

    gzip — не мікрооптимізація. Виміряно на 5 крамницях: 988 КБ → 112 КБ (**8.8×**;
    Rozetka 10.9×, Allo 9.9×). На 2.5 млн товарів це різниця між 138 ТБ/міс (жоден
    дешевий хост) і 15.7 ТБ/міс (базовий тариф). Найдешевший важіль масштабу, що є.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "uk,en;q=0.9",
        "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return decode_body(r.read(), r.headers.get("Content-Encoding"))


def _collect_source(conn, src, categories, fetch, delay) -> dict:
    """Один прохід по джерелу. НЕ кидає: падіння однієї крамниці не має валити решту
    (на 10-50 крамницях це був би щоденний обвал). Повертає звіт для виклику.

    `scan_run` створюється песимістично зі status='failed' і стає 'ok' лише в кінці:
    якщо процес помре посеред проходу, у БД лишиться чесне 'failed', а не бадьора
    брехня. Раніше рядок писався одразу як 'ok' — і провал виглядав успіхом (T13).
    """
    name = src["name"]
    source_id = upsert_source(conn, name, src["base_url"], adapter_kind="ssr",
                              platform=src.get("platform"),
                              discount_url=src["discount_urls"][0],
                              fetch_tier=src.get("fetch_tier"))
    scan_run_id = conn.execute(
        "INSERT INTO scan_run (source_id, surface, status) VALUES (%s,'discovery','failed') "
        "RETURNING scan_run_id", (source_id,)).fetchone()[0]

    # Дворівневий discovery (Allo-клас): discount_urls[0] — ХАБ, адаптер.discover(хаб)
    # віддає справжні сторінки-лендинги. Падіння хаба = failed одразу (сторінок нема звідки взяти).
    urls = list(src["discount_urls"])
    errors: list[str] = []
    if src.get("hub_discovery"):
        try:
            urls = src["adapter"].discover(fetch(urls[0]))[:src.get("max_pages", 20)]
            if delay:
                time.sleep(delay)
            if not urls:
                errors.append(f"{src['discount_urls'][0]}: discover() віддав 0 сторінок")
        except Exception as e:
            errors.append(f"hub {src['discount_urls'][0]}: {type(e).__name__}: {e}")
            urls = []

    items, seen = [], set()
    for i, url in enumerate(urls):
        if i and delay:
            time.sleep(delay)                            # ввічливість між сторінками хоста
        try:
            got = src["adapter"].extract(fetch(url))
        except Exception as e:                           # мережа/парсер — інші URL мають шанс
            errors.append(f"{url}: {type(e).__name__}: {e}")
            continue
        for it in got:
            if it.external_ref in seen:                  # дедуп між сторінками (§10.1)
                continue
            seen.add(it.external_ref)
            items.append(it)

    try:
        n = persist_items(conn, source_id, items, categories,
                          source_method="css", scan_run_id=scan_run_id)
    except Exception as e:
        errors.append(f"persist: {type(e).__name__}: {e}")
        n = 0

    ok_urls = max(len(urls), 1) - len(errors)
    status = "failed" if ok_urls == 0 else ("partial" if errors else "ok")
    conn.execute("UPDATE scan_run SET finished_at = now(), items_seen = %s, status = %s "
                 "WHERE scan_run_id = %s", (n, status, scan_run_id))
    return {"source": name, "items": n, "status": status, "errors": errors}


def collect(conn, sources, fetch=default_fetch, delay=POLITE_DELAY) -> dict:
    """Discovery-прохід + detect_pass + закриття зниклих.

    `problems` — джерела, які впали АБО віддали нуль. Нуль підозрілий сам по собі:
    відрізнити «акцій справді нема» від «селектор помер» з одного проходу не можна,
    тому кажемо про це вголос, а не ховаємо за status='ok'.
    """
    categories = load_categories(conn)          # slug→id; категорія на товар — за URL (§2.6)
    per_source, disabled = [], []
    for src in sources:
        if not src.get("enabled", True):        # свідомо вимкнене (причина — коментар у SOURCES)
            disabled.append(src["name"])
            continue
        try:
            per_source.append(_collect_source(conn, src, categories, fetch, delay))
        except Exception as e:                  # остання сітка: джерело не валить прохід
            per_source.append({"source": src["name"], "items": 0, "status": "failed",
                               "errors": [f"{type(e).__name__}: {e}"]})

    events = detect_pass(conn)                            # бейджі після збору (§8.4)
    closed = close_absent(conn)                           # закрити зниклі з акцій (§5.5)
    return {"items": sum(r["items"] for r in per_source), "events": events, "closed": closed,
            "sources": len(per_source), "disabled": disabled, "per_source": per_source,
            "problems": [r for r in per_source if r["status"] != "ok" or r["items"] == 0]}


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("SKIP collect: DATABASE_URL не задано (потрібна ПОСТІЙНА БД — Neon + Actions secret).")
        return
    import psycopg
    migrate.apply(url)
    with psycopg.connect(url, autocommit=True) as conn:
        stats = collect(conn, SOURCES)

    for r in stats["per_source"]:
        print(f"  {r['source']:12} {r['items']:>4} позицій  [{r['status']}]")
        for e in r["errors"]:
            print(f"      ! {e}")
    for name in stats.get("disabled", []):
        print(f"  {name:12}    — вимкнено свідомо (причина в SOURCES)")
    print(f"колект: items={stats['items']} events={stats['events']} closed={stats['closed']}")

    # Мовчазний нуль — головний спосіб, у який збір гниє непоміченим: cron «зелений»,
    # даних нема. Краще червоний прогін і хибна тривога, ніж тиша (T13).
    if stats["problems"]:
        print("\nПРОВАЛ: джерела без даних або з помилками — "
              + ", ".join(f"{r['source']}({r['items']}, {r['status']})" for r in stats["problems"]))
        sys.exit(1)


if __name__ == "__main__":
    main()
