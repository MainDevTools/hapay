#!/usr/bin/env python3
"""Колектор (Шар 1, §8.1): fetch → extract → persist → detect_pass.

Один прогін = один discovery-scan по кожному джерелу: заводить scan_run, тягне
discovery-URL(и), екстрактить RawItem, персистить у price_snapshot, наприкінці
рахує бейджі (detect_pass). Scheduled GH-workflow ганяє наживо в постійну БД;
CI-тест підставляє касету через параметр `fetch` (детерміновано, без живого HTTP).

Секрет `DATABASE_URL` — лише з env (Actions secret); ніколи в репо (git-безпека §8).
"""
from __future__ import annotations
import os
import sys
import time
import urllib.request

from adapters.pethouse import PethouseAdapter
from adapters.petchoice import PetChoiceAdapter
from db import migrate
from db.store import upsert_source, persist_items
from detection.runner import detect_pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
POLITE_DELAY = 3.0          # §10.2 — пауза між запитами до одного хоста

# Реєстр джерел (discovery §3.3, тир A). Категорія — uncategorized (реальна таксономія — далі).
SOURCES = [
    {"name": "Pethouse", "base_url": "https://pethouse.ua", "platform": "custom",
     "fetch_tier": "A", "adapter": PethouseAdapter(), "category_slug": "uncategorized",
     "discount_urls": ["https://pethouse.ua/ua/shop/koshkam/suhoi-korm/akcii/"]},
    {"name": "PetChoice", "base_url": "https://petchoice.ua", "platform": "custom",
     "fetch_tier": "A", "adapter": PetChoiceAdapter(), "category_slug": "uncategorized",
     "discount_urls": ["https://petchoice.ua/discounts"]},
]


def default_fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "uk,en;q=0.9", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _category_id(conn, slug: str) -> int:
    return conn.execute("SELECT category_id FROM category WHERE slug = %s", (slug,)).fetchone()[0]


def collect(conn, sources, fetch=default_fetch) -> dict:
    """Discovery-прохід по джерелах + detect_pass. Повертає {items, events, sources}."""
    total_items = 0
    for src in sources:
        source_id = upsert_source(conn, src["name"], src["base_url"], adapter_kind="ssr",
                                  platform=src.get("platform"),
                                  discount_url=src["discount_urls"][0],
                                  fetch_tier=src.get("fetch_tier"))
        category_id = _category_id(conn, src["category_slug"])
        scan_run_id = conn.execute(
            "INSERT INTO scan_run (source_id, surface, status) VALUES (%s,'discovery','ok') "
            "RETURNING scan_run_id", (source_id,)).fetchone()[0]

        items, seen = [], set()
        for i, url in enumerate(src["discount_urls"]):
            if i:
                time.sleep(POLITE_DELAY)                 # ввічливість між сторінками хоста
            for it in src["adapter"].extract(fetch(url)):
                if it.external_ref in seen:              # дедуп між сторінками (§10.1)
                    continue
                seen.add(it.external_ref)
                items.append(it)

        n = persist_items(conn, source_id, category_id, items,
                          source_method="css", scan_run_id=scan_run_id)
        conn.execute("UPDATE scan_run SET finished_at = now(), items_seen = %s WHERE scan_run_id = %s",
                     (n, scan_run_id))
        total_items += n

    events = detect_pass(conn)                            # бейджі після збору (§8.4)
    return {"items": total_items, "events": events, "sources": len(sources)}


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("SKIP collect: DATABASE_URL не задано (потрібна ПОСТІЙНА БД — Timescale Cloud + Actions secret).")
        return
    import psycopg
    migrate.apply(url)
    with psycopg.connect(url, autocommit=True) as conn:
        stats = collect(conn, SOURCES)
    print(f"колект: {stats}")


if __name__ == "__main__":
    main()
