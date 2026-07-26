"""Серверний колектор: сервер бере з черги те, що вміє сам (S23).

## Навіщо

Кореневий блокер проєкту — стеля збору. Заміряно 2026-07-26: у черзі 2244 задачі,
з них **1073 жодного разу не збирали**, ~86 за добу з одного телефона; повний оберт
≈26 днів, тобто для статутного 30-денного вікна історії просто нема з чого рахувати
(звідси `verified = 0` при 23 тис. `declared`).

Але припущення «збирати може лише телефон» ніхто не перевіряв від липня. Серійна
перевірка з ДЦ-IP сервера (3 запити на крамницю, повний розмір сторінки):

    пускають: Moyo, Citrus, Epicentr, Vencon, Telemart, Podorozhnyk, Apteka911,
              KTC, Storgom, MedMagazin, Fotosale, Interatletika, Antoshka,
              DniproM, Yabko, Zootovary                      — 16 крамниць
    блокують: Allo, Foxtrot, Rozetka, Stylus, MAUDAU (403), Autopresent (429)

На ці 16 припадає **838 із 2244 задач (37%)**, з них 270 не збирали ЖОДНОГО разу.
Сервер завжди ввімкнений — на відміну від телефона, що спить разом із пристроєм.

## Чому саме такий шлях

Колектор ходить у ВЛАСНЕ API рівно так само, як телефон: `lease` → GET сторінки →
`ingest/html`. Спокуса зробити «швидше, в процесі» відкинута: ендпойнт `ingest_html`
несе не лише розбір, а й чергу нащадків, детекцію та обробку «тихого нуля». Другий
шлях повз нього неминуче розійшовся б із першим — і розбіжність вилізла б місяцями
пізніше на живих даних.

Що НЕ робимо:
* не беремо render-крамниці (WebView на сервері нема) і ті 6, що блокують ДЦ, — для
  цього оренда приймає список `sources`; інакше сервер тягнув би задачі, які
  гарантовано провалить, і псував би їм лічильник збоїв замість лишити телефону;
* не обходимо анти-бот: 403 = «нам сюди не можна», крапка (§7.4);
* не прискорюємо темп на крамницю — розліт 15 хв тримає сама черга.

Запуск: `python collect_server.py [--limit N] [--passes N]`; на сервері — systemd-таймер.
"""
from __future__ import annotations

import argparse
import gzip
import os
import sys
import time
import urllib.error
import urllib.request

# Крамниці, які ПУСКАЮТЬ ДЦ-IP (перевірено серійно 2026-07-26 з самого сервера).
# ⚠ Вердикти протухають: анти-бот міняють, і крамниця з цього списку може почати
# віддавати 403 або, гірше, порожню сторінку зі статусом 200. Перевіряти серійно
# (3 запити), а не одним — перший запит часто пускають і блокують наступні.
DC_OK = [
    "Moyo", "Citrus", "Epicentr", "Vencon", "Telemart", "Podorozhnyk", "Apteka911",
    "KTC", "Storgom", "MedMagazin", "Fotosale", "Interatletika", "Antoshka",
    "DniproM", "Yabko", "Zootovary",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MAX_HTML = 4_000_000          # та сама стеля, що в застосунку — сторінка більша за це підозріла
FETCH_TIMEOUT = 25


def _api_base() -> str:
    return os.environ.get("HAPAY_API", "http://127.0.0.1:8080").rstrip("/")


def _token() -> str:
    """Токен колектора з INGEST_TOKENS (`мітка:секрет`, кома-розділені) — той самий
    механізм, що для сателітів S10. Без нього не працюємо: мовчазний збір без
    провенансу гірший за його відсутність."""
    raw = os.environ.get("INGEST_TOKENS", "").strip()
    if not raw:
        sys.exit("INGEST_TOKENS не заданий — серверний колектор не має чим представитись")
    first = raw.split(",")[0]
    return first.split(":", 1)[1] if ":" in first else first


def _api(path: str, payload: dict | None = None, token: str = "") -> dict:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        import json
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(_api_base() + path, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    import json
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b"{}")


def fetch(url: str) -> str:
    """Звичайний GET зі стелею розміру. Помилка — виняток; викликач її фіксує в черзі."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "uk,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        raw = r.read(MAX_HTML + 1)
        if len(raw) > MAX_HTML:
            raise ValueError("сторінка завелика")
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def one_pass(token: str, limit: int) -> tuple[int, int, list[str]]:
    """Один прохід: узяти задачі → зібрати → віддати серверу. (задач, прийнято, помилки)"""
    lease = _api("/api/collect/lease", {"limit": limit, "sources": DC_OK}, token)
    tasks = lease.get("tasks", [])
    accepted, errors = 0, []
    for t in tasks:
        try:
            html = fetch(t["url"])
        except Exception as e:                       # мережа/403/таймаут — це збій ЗАДАЧІ
            errors.append(f"{t['source']}: {type(e).__name__}")
            try:
                _api("/api/collect/fail", {"task_id": t["task_id"],
                                           "reason": type(e).__name__[:60]}, token)
            except Exception:
                pass
            continue
        try:
            r = _api("/api/ingest/html", {"source": t["source"], "url": t["url"],
                                          "html": html, "task_id": t["task_id"]}, token)
            accepted += int(r.get("accepted") or 0)
        except Exception as e:
            errors.append(f"{t['source']}: інджест {type(e).__name__}")
    return len(tasks), accepted, errors


def main() -> int:
    ap = argparse.ArgumentParser(description="серверний колектор (крамниці, що пускають ДЦ)")
    ap.add_argument("--limit", type=int, default=16, help="задач за прохід (≤1 на крамницю)")
    ap.add_argument("--passes", type=int, default=3, help="проходів за запуск")
    ap.add_argument("--sleep", type=float, default=20.0, help="пауза між проходами, с")
    a = ap.parse_args()

    token = _token()
    total_t = total_a = 0
    for i in range(a.passes):
        n, acc, errs = one_pass(token, a.limit)
        total_t += n
        total_a += acc
        print(f"прохід {i + 1}/{a.passes}: задач {n}, прийнято {acc}"
              + (f", збоїв {len(errs)}: {'; '.join(errs[:4])}" if errs else ""))
        if n == 0:
            print("  черга порожня для наших крамниць — виходимо")
            break
        if i + 1 < a.passes:
            time.sleep(a.sleep)
    print(f"разом: задач {total_t}, прийнято позицій {total_a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
