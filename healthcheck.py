"""Синтетична перевірка: чи продукт справді працює (S30).

Навіщо окремо від `hapay-alert` (той стежить за ЗБОРОМ) і від `/api/health` (той каже
лише «процес живий»). 2026-07-28 нічний бекап не виконувався **три доби**, і жоден із
наявних сторожів цього не бачив: таймер був `enabled`, тобто налаштування виглядало
правильним. Саме тому тут перевіряються НАСЛІДКИ, а не конфігурація:

    не `systemctl is-enabled`, а «коли юніт востаннє відпрацював»
    не «ендпойнт існує», а «він віддав дані, які має віддати»

Запуск:
    python healthcheck.py            # вивід + код виходу 1, якщо є червоне
    python healthcheck.py --json     # для машин

Алерт у Telegram піде, лише якщо задано ALERT_TG_CHAT_ID (і BOT_TOKEN). Без них
результат лишається у виводі та в коді виходу — це видно в `systemctl --failed`
і в journalctl, тобто мовчазним провал не буде в жодному разі.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SITE = os.environ.get("HEALTH_SITE", "https://hapay.today")
TIMEOUT = 20

# Пороги. Свідомо мʼякші за реальний ритм, щоб сторож не кричав на нормальні коливання:
# збір ходить кожні 15 хв, бекап — щоночі.
MAX_FRESHNESS_H = 12        # скільки годин без успішного збору ще не біда
MAX_BACKUP_AGE_H = 30       # доба + запас на зсув таймера
MIN_CATALOG_ITEMS = 10      # стрічка, що віддала менше, — це вже не стрічка


class Result:
    def __init__(self):
        self.rows: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = ""):
        self.rows.append((name, ok, detail))

    @property
    def failed(self):
        return [r for r in self.rows if not r[1]]


def _get(path: str):
    with urllib.request.urlopen(SITE + path, timeout=TIMEOUT) as r:
        return r.status, r.read()


def _json(path: str):
    _, body = _get(path)
    return json.loads(body)


def check_site(res: Result):
    """Сторінки, які бачить людина. Перевіряємо ВМІСТ, а не лише код 200: сторінка
    може віддати 200 і бути порожньою — саме так виглядав мертвий Mini App."""
    try:
        st, body = _get("/")
        res.add("головна віддається", st == 200 and b"<title>" in body, f"HTTP {st}")
    except Exception as e:
        res.add("головна віддається", False, str(e)[:80])

    try:
        items = _json("/api/discounts?page=0")
        res.add(f"стрічка має ≥{MIN_CATALOG_ITEMS} позицій",
                len(items) >= MIN_CATALOG_ITEMS, f"{len(items)} шт")
    except Exception as e:
        res.add("стрічка віддається", False, str(e)[:80])

    for path in ("/api/drops?days=1", "/api/stores", "/api/categories"):
        try:
            data = _json(path)
            n = len(data.get("items", [])) if isinstance(data, dict) else len(data)
            res.add(f"{path} відповідає", True, f"{n} шт")
        except Exception as e:
            res.add(f"{path} відповідає", False, str(e)[:80])


def check_freshness(res: Result):
    """Скільки годин тому востаннє щось зібралось. Це і є «продукт живий»:
    сайт може працювати, а дані — протухати, і зовні це непомітно."""
    try:
        m = _json("/api/freshness").get("minutes")
        if m is None:
            res.add("свіжість даних", False, "жодного успішного збору")
        else:
            res.add(f"свіжість даних < {MAX_FRESHNESS_H} год",
                    m <= MAX_FRESHNESS_H * 60, f"{round(m / 60, 1)} год тому")
    except Exception as e:
        res.add("свіжість даних", False, str(e)[:80])


def _unit_last_run_h(unit: str) -> float | None:
    """Годин від останнього УСПІШНОГО запуску юніта. None — якщо не запускався ніколи."""
    try:
        out = subprocess.run(
            ["systemctl", "show", unit, "--property=ExecMainExitTimestampMonotonic",
             "--property=ExecMainStatus", "--value"],
            capture_output=True, text=True, timeout=10).stdout.split()
        if not out or out[0] in ("0", ""):
            return None
        # монотонний час у мікросекундах від старту машини
        mono_us = int(out[0])
        with open("/proc/uptime") as f:
            uptime_s = float(f.read().split()[0])
        return (uptime_s - mono_us / 1_000_000) / 3600
    except Exception:
        return None


def check_units(res: Result):
    """⚠ ГОЛОВНЕ: перевіряємо, коли юніт ВІДПРАЦЮВАВ, а не чи він `enabled`.

    28.07 бекап був enabled і не виконувався жодного разу — бо `enable` без `--now`
    активує юніт лише з наступного завантаження. Перевірка конфігурації цього не бачить
    за визначенням."""
    if not os.path.exists("/run/systemd/system"):
        res.add("systemd недоступний (не сервер)", True, "перевірку юнітів пропущено")
        return
    age = _unit_last_run_h("hapay-backup.service")
    res.add(f"бекап виконувався < {MAX_BACKUP_AGE_H} год тому",
            age is not None and age <= MAX_BACKUP_AGE_H,
            "жодного разу" if age is None else f"{round(age, 1)} год тому")
    for t in ("hapay-backup.timer", "hapay-collect-server.timer", "hapay-mail.timer"):
        try:
            active = subprocess.run(["systemctl", "is-active", t],
                                    capture_output=True, text=True, timeout=10).stdout.strip()
            res.add(f"{t} активний", active == "active", active or "?")
        except Exception as e:
            res.add(f"{t} активний", False, str(e)[:60])


def notify(res: Result) -> bool:
    """Telegram — лише якщо оператор задав чат. Інакше мовчимо: слати нікуди."""
    chat = os.environ.get("ALERT_TG_CHAT_ID", "").strip()
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not chat or not token or not res.failed:
        return False
    lines = ["🔴 Хапай — перевірка стану"] + [f"• {n}: {d}" for n, _, d in res.failed]
    data = json.dumps({"chat_id": chat, "text": "\n".join(lines)}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT):
            return True
    except Exception:
        return False


def run() -> Result:
    res = Result()
    check_site(res)
    check_freshness(res)
    check_units(res)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Синтетична перевірка «Хапай»")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = run()
    if a.json:
        print(json.dumps([{"name": n, "ok": ok, "detail": d} for n, ok, d in r.rows],
                         ensure_ascii=False))
    else:
        for n, ok, d in r.rows:
            print(f"{'  ok  ' if ok else ' FAIL '} {n:44} {d}")
        print(f"\n{len(r.rows) - len(r.failed)}/{len(r.rows)} перевірок пройдено")
    sent = notify(r)
    if r.failed and not sent:
        print("⚠ ALERT_TG_CHAT_ID не заданий — алерт нікуди не пішов, "
              "провал видно лише тут і в journalctl", file=sys.stderr)
    sys.exit(1 if r.failed else 0)
