#!/usr/bin/env python
"""PC-колектор: збір fetch-крамниць із резидентного IP оператора, ОКРЕМО від застосунку.

Навіщо. Доти збір жив у MAUI-застосунку, тож кожна зміна UI → перезбірка → колектор
їде разом, а на емуляторі він ще й тихо вмирав (DNS, прибитий процес — двічі за день
2026-07-22). Черга-оренда (T16) навмисно приймає БУДЬ-ЯКОГО робітника, тож колектором
може бути цей скрипт: він опитує чергу, тягне сторінки звичайним GET зі свого
резидентного IP (крамниці його не блокують — та сама причина, чому працює телефон) і
шле серверу. Вся валідація/парсинг лишаються на сервері — тут ЛИШЕ транспорт.

Межа. Бере ЛИШЕ `fetch`-крамниці (`modes=['fetch']` в оренді) — render (add.ua/Comfy/
Brain/Eldorado) лишається телефону, бо потребує WebView. Так два робітники (телефон+PC)
ділять чергу за здатністю, не крадучи задач одне в одного.

Запуск:
    HAPAY_COLLECTOR_TOKEN=<токен> python tools/pc_collector.py            # цикл
    HAPAY_COLLECTOR_TOKEN=<токен> python tools/pc_collector.py --once      # один прохід
Токен: env `HAPAY_COLLECTOR_TOKEN` або файл `tools/.pc_collector_token` (у .gitignore —
секрет НЕ в репо). Це той самий bearer-токен, що в INGEST_TOKENS на сервері (окремий
label `pc`, щоб відкликати незалежно від телефона).

Persistent-запуск (Windows Scheduled Task) — команду дає README; сам скрипт систему не
чіпає.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("HAPAY_BASE", "https://hapay.today").rstrip("/")
LEASE_LIMIT = 12               # просимо більше, ніж крамниць: оренда однак дає ≤1/крамницю
PASS_SLEEP = 60                # сон між проходами; сервер сам тримає розліт 15 хв/крамниця
POLITE = 2.0                   # пауза між запитами до РІЗНИХ хостів (§10.2)
FETCH_TIMEOUT = 30
MAX_HTML = 8_000_000           # під серверною стелею (12 МБ), із запасом
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def load_token() -> str:
    tok = os.environ.get("HAPAY_COLLECTOR_TOKEN", "").strip()
    if not tok:
        f = pathlib.Path(__file__).with_name(".pc_collector_token")
        if f.exists():
            tok = f.read_text(encoding="utf-8").strip()
    if not tok:
        sys.exit("Нема токена: задай HAPAY_COLLECTOR_TOKEN або поклади tools/.pc_collector_token")
    return tok


def _referer(url: str) -> str:
    return "/".join(url.split("/")[:3]) + "/"


class HapayClient:
    """Транспорт до сервера (lease/ingest/fail) + фетч крамниці. Мережа лише тут —
    ядро run_pass бере це абстракцією, тож тестується без мережі."""

    def __init__(self, token: str, base: str = BASE):
        self.base, self.token = base, token

    def _api(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))

    def lease(self, limit: int, modes: list[str]) -> list[dict]:
        return self._api("/api/collect/lease", {"limit": limit, "modes": modes}).get("tasks", [])

    def ingest(self, source: str, url: str, html: str, task_id: int) -> dict:
        return self._api("/api/ingest/html",
                         {"source": source, "url": url, "html": html, "task_id": task_id})

    def fail(self, task_id: int, note: str) -> None:
        self._api("/api/collect/fail", {"task_id": task_id, "note": note})

    def fetch(self, url: str) -> str:
        """GET сторінки крамниці резидентними заголовками. Помилка → виняток (→ fail)."""
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept-Language": "uk,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": _referer(url)})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
            raw = r.read(MAX_HTML)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")


def run_pass(client, limit: int = LEASE_LIMIT, polite=lambda: time.sleep(POLITE)) -> tuple[int, int]:
    """Один прохід: оренда fetch-задач → тягнути → ingest; помилка задачі → fail.

    ЧИСТЕ ЯДРО: `client` — будь-що з lease/fetch/ingest/fail, тож у тесті це фейк.
    Помилка ОДНІЄЇ задачі не валить прохід (крихкість емулятора починалась саме з
    того, що один збій зупиняв усе). Повертає (успішних, збійних).
    """
    tasks = client.lease(limit=limit, modes=["fetch"])
    ok = failed = 0
    for i, t in enumerate(tasks):
        if t.get("mode") not in (None, "fetch"):    # захист: render не тягнемо GET-ом
            continue
        try:
            html = client.fetch(t["url"])
            client.ingest(t["source"], t["url"], html, t["task_id"])
            ok += 1
        except Exception as e:                        # noqa: BLE001 — навмисно широко: транспорт
            try:
                client.fail(t["task_id"], f"{type(e).__name__}: {e}"[:200])
            except Exception:
                pass                                  # не змогли й повідомити збій — оренда протухне сама
            failed += 1
        if i < len(tasks) - 1:
            polite()
    return ok, failed


def _log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="PC-колектор Хапая (fetch-режим)")
    ap.add_argument("--once", action="store_true", help="один прохід і вихід (для тесту)")
    args = ap.parse_args()
    client = HapayClient(load_token())
    _log(f"старт · {BASE} · fetch-режим")
    while True:
        try:
            ok, failed = run_pass(client)
            if ok or failed:
                _log(f"прохід: зібрано {ok}, збоїв {failed}")
        except urllib.error.URLError as e:
            _log(f"мережа недоступна: {e} — повтор за {PASS_SLEEP}с")
        except Exception as e:                        # noqa: BLE001 — цикл НЕ падає ніколи
            _log(f"неочікувано: {type(e).__name__}: {e} — цикл триває")
        if args.once:
            break
        time.sleep(PASS_SLEEP)


if __name__ == "__main__":
    main()
