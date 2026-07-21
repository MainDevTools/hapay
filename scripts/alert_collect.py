#!/usr/bin/env python
"""Сторож збору: помічає, що колектор замовк, і повідомляє — один раз на подію.

НАВІЩО. 2026-07-21 збір стояв дві години, і побачив це людина, яка випадково
дивилась у базу. Показник у профілі, доданий того ж дня, пасивний: його треба
відкрити. Якщо телефон помре вночі, до ранку ніхто не дізнається, а застосунок
показуватиме вчорашні ціни як поточні — рівно те, за що ми критикуємо крамниці.

ЧОМУ НА СЕРВЕРІ. Застосунок не може попередити про власну смерть. Сторож мусить
жити там, де він переживе колектор, — у systemd-таймері поруч із бекапом.

КАНАЛ НЕОБОВ'ЯЗКОВИЙ. Без BOT_TOKEN/ALERT_TG_CHAT_ID сторож усе одно працює:
фіксує падіння й відновлення в ops_alert. Ввімкнути надсилання — дві змінні в
/etc/hapay/hapay.env, без зміни коду. Так фіча корисна вже сьогодні й не тримає
нас у заручниках зовнішнього сервісу (§O — вибір сервісів за власником).

Запуск:
    python scripts/alert_collect.py              # перевірка (так її кличе таймер)
    python scripts/alert_collect.py --whoami     # знайти свій chat_id для налаштування
    python scripts/alert_collect.py --dry-run    # показати рішення, нічого не слати
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ALERT_NAME = "collect_silent"

# Скільки чекати, перш ніж нагадати про ТРИВАЮЧУ зупинку. Одне повідомлення на подію —
# добре, але якщо збій тягнеться добу, про нього варто нагадати. Не частіше: сторож,
# який дзвонить щочверть години, вимикається людиною на другий день, і тоді він марний.
REMIND_HOURS = 6


def decide(prev: dict | None, healthy: bool, now: datetime,
           remind_hours: int = REMIND_HOURS) -> tuple[str, str | None]:
    """ЧИСТА логіка сторожа → (новий_стан, що_слати|None).

    Тримаємо окремо від БД і мережі, щоб тестувати без обох: саме тут ховаються
    помилки на кшталт «шле щоразу» або «мовчить назавжди після першого разу».
    """
    state = "ok" if healthy else "down"
    prev_state = (prev or {}).get("state")

    if prev_state == state:
        if state == "down":                       # триває — нагадуємо, але рідко
            last = (prev or {}).get("last_sent_at")
            if last is None or now - last >= timedelta(hours=remind_hours):
                return state, "reminder"
        return state, None                        # без змін — мовчимо

    if state == "down":
        return state, "down"                      # щойно впало
    if prev_state is None:
        return state, None                        # перший запуск і все гаразд — не шумимо
    return state, "recovered"                     # піднялось


def _message(kind: str, health: dict, domain: str) -> str:
    head = {
        "down": "🔴 Хапай: збір зупинився",
        "reminder": "🔴 Хапай: збір досі стоїть",
        "recovered": "🟢 Хапай: збір відновився",
    }[kind]
    return (f"{head}\n{health.get('note', '')}\n"
            f"{health.get('tasks_done_1h', 0)} задач за годину · "
            f"{health.get('tasks_done_24h', 0)} за добу з {health.get('tasks_total', 0)}\n"
            f"{domain}")


def _tg(method: str, params: dict) -> dict | None:
    """Виклик Telegram Bot API на stdlib. Мовчки повертає None, якщо токена нема."""
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            return json.load(r)
    except urllib.error.URLError as e:
        print(f"[alert] Telegram недоступний: {e}", file=sys.stderr)
        return None


def whoami() -> int:
    """Показати chat_id тих, хто нещодавно писав боту — щоб було що вписати в env.
    Секрет не друкуємо: лише id та ім'я."""
    res = _tg("getUpdates", {"limit": 20})
    if res is None:
        print("BOT_TOKEN не заданий — спершу створи бота в @BotFather і додай токен "
              "у /etc/hapay/hapay.env")
        return 1
    chats = {}
    for u in res.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        ch = msg.get("chat") or {}
        if ch.get("id"):
            chats[ch["id"]] = ch.get("username") or ch.get("first_name") or ch.get("title") or "?"
    if not chats:
        print("Нема свіжих повідомлень. Напиши щось своєму боту в Telegram і повтори.")
        return 1
    print("Знайдені чати (додай потрібний як ALERT_TG_CHAT_ID):")
    for cid, who in chats.items():
        print(f"  {cid}  —  {who}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--whoami", action="store_true", help="показати chat_id зі свіжих повідомлень")
    ap.add_argument("--dry-run", action="store_true", help="вирішити, але не слати й не писати")
    args = ap.parse_args()

    if args.whoami:
        return whoami()

    import psycopg
    from psycopg.rows import dict_row
    from api import qtasks

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("нема DATABASE_URL", file=sys.stderr)
        return 2

    with psycopg.connect(dsn, autocommit=True) as conn:
        health = qtasks.collect_health(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            prev = cur.execute("SELECT * FROM ops_alert WHERE name = %s",
                               (ALERT_NAME,)).fetchone()
        now = datetime.now(timezone.utc)
        state, kind = decide(prev, bool(health.get("ok")), now)

        print(f"[alert] стан={state} дія={kind or 'нічого'} · {health.get('note')}")
        if args.dry_run:
            return 0

        sent = False
        if kind:
            chat = os.environ.get("ALERT_TG_CHAT_ID")
            domain = os.environ.get("HAPAY_DOMAIN", "hapay.today")
            if chat:
                res = _tg("sendMessage", {"chat_id": chat,
                                          "text": _message(kind, health, domain)})
                sent = bool(res and res.get("ok"))
                if not sent:
                    print("[alert] не вдалося надіслати — канал не налаштований або збій",
                          file=sys.stderr)
            else:
                print("[alert] канал не налаштований (нема ALERT_TG_CHAT_ID) — лише пишу стан")

        # Стан пишемо ЗАВЖДИ, навіть коли надіслати не вдалося: інакше сторож забуде
        # про падіння й повторить спробу як «нове», і так по колу.
        changed = prev is None or prev["state"] != state
        conn.execute(
            """INSERT INTO ops_alert (name, state, changed_at, last_sent_at, sent_count, note)
               VALUES (%s, %s, now(), CASE WHEN %s THEN now() END, %s, %s)
               ON CONFLICT (name) DO UPDATE SET
                 state = EXCLUDED.state,
                 changed_at = CASE WHEN ops_alert.state <> EXCLUDED.state
                                   THEN now() ELSE ops_alert.changed_at END,
                 last_sent_at = CASE WHEN %s THEN now() ELSE ops_alert.last_sent_at END,
                 sent_count = ops_alert.sent_count + CASE WHEN %s THEN 1 ELSE 0 END,
                 note = EXCLUDED.note""",
            (ALERT_NAME, state, sent, 1 if sent else 0, health.get("note"), sent, sent))
        if changed:
            print(f"[alert] стан змінився на «{state}»")
    return 0


if __name__ == "__main__":
    sys.exit(main())
