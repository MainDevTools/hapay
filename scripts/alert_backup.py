#!/usr/bin/env python
"""OnFailure-хук нічного бекапу: гучний журнал + Telegram (якщо канал є).

НАВІЩО. Тихий провал бекапу — це катастрофа 17.07 навпаки: думаєш, історія цін у
безпеці офсайт, а копії щоночі не з'являються (змінились ключі, повне призначення,
впала мережа). Історію НЕ зібрати заднім числом. systemd кличе це при падінні
hapay-backup.service (OnFailure=).

КАНАЛ НЕОБОВ'ЯЗКОВИЙ (той самий принцип, що в alert_collect): без BOT_TOKEN/
ALERT_TG_CHAT_ID хук усе одно кричить у журнал і робить юніт `failed` (видно в
`systemctl --failed`); з каналом — активний пуш у Telegram.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _tg(method: str, params: dict) -> dict | None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            return json.load(r)
    except urllib.error.URLError as e:
        print(f"[backup-alert] Telegram недоступний: {e}", file=sys.stderr)
        return None


def main() -> int:
    domain = os.environ.get("HAPAY_DOMAIN", "hapay.today")
    print("[backup-alert] 🔴 НІЧНИЙ БЕКАП ВПАВ — історія цін без свіжої офсайт-копії",
          file=sys.stderr)
    chat = os.environ.get("ALERT_TG_CHAT_ID")
    if not chat:
        print("[backup-alert] нема ALERT_TG_CHAT_ID — лише журнал (systemctl --failed)",
              file=sys.stderr)
        return 0
    res = _tg("sendMessage", {"chat_id": chat, "text":
              "🔴 Хапай: НІЧНИЙ БЕКАП ВПАВ\n"
              "Історія цін лишилась без свіжої офсайт-копії.\n"
              "Перевір: journalctl -u hapay-backup -n 50\n"
              f"{domain}"})
    if not (res and res.get("ok")):
        print("[backup-alert] канал не спрацював (токен/chat_id?)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
