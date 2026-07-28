"""Розсилка листів про зниження цін (S29).

Навіщо. «Стежити за ціною» досі означало сповіщення ЛИШЕ на Android (локальні
нотифікації WorkManager). Для веба й для Telegram Mini App не було нічого: треба було
самому зайти в кабінет і подивитись. При цьому труба для листів уже прокладена —
Resend із верифікованим доменом, — і використовувалась тільки для транзакційних.

Запускати після збору:
    python alerts.py --dry-run      # показати, що пішло б, і НЕ слати
    python alerts.py                # надіслати

⚠ Три запобіжники, бо це листи людям, а не рядок у логу:
  1. Пишемо лише тим, хто ПІДТВЕРДИВ пошту й не вимкнув листи (`users_for_alerts`).
  2. Не частіше ніж раз на `MIN_HOURS` на людину — інакше кожен прохід збору давав би
     новий лист про ту саму хвилю знижень.
  3. Пам'ять про надіслане оновлюємо ЛИШЕ після успішної відправки: якщо SMTP упав,
     наступний прохід спробує знову, а не «забуде» мовчки.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.pool import get_pool          # noqa: E402
from api import db as qdb             # noqa: E402
from api import email as qemail       # noqa: E402
from api import auth as qauth         # noqa: E402

# Не частіше одного листа на людину за цей проміжок. Збір ходить кілька разів на добу,
# а зниження приходять хвилями — без паузи людина отримала б лист після кожного проходу.
MIN_HOURS = 12
# Стеля позицій у листі: довший лист не читають, а коротший чесніший — решта в кабінеті.
MAX_ITEMS = 10


def _recent_alert(conn, user_id: int, hours: int) -> bool:
    """Чи писали цій людині нещодавно. Спираємось на `alert_sent` і `last_notified_at`:
    перше — стеження за запитом, друге — за товаром."""
    row = conn.execute(
        "SELECT EXISTS ("
        "  SELECT 1 FROM alert_sent a JOIN watchlist w USING (watchlist_id)"
        "   WHERE w.user_id = %s AND a.sent_at > now() - make_interval(hours => %s)"
        "  UNION ALL"
        "  SELECT 1 FROM watchlist w"
        "   WHERE w.user_id = %s AND w.last_notified_at > now() - make_interval(hours => %s))",
        (user_id, hours, user_id, hours)).fetchone()
    return bool(row and row[0])


def collect_for_user(conn, user_id: int) -> list[dict]:
    """Що саме сказати цій людині: зниження по товарах + влучання по запитах."""
    items = list(qdb.list_price_drops(conn, user_id))
    for h in qdb.query_watch_hits(conn, user_id):
        items.append({"title": h["title"], "current_kop": h["current_kop"],
                      "store": h["store"], "store_product_id": h["store_product_id"],
                      "target_kop": h["target_kop"], "watchlist_id": h["watchlist_id"],
                      "query": True})
    return items[:MAX_ITEMS]


def run(dry_run: bool = False, min_hours: int = MIN_HOURS) -> dict:
    sent = skipped = failed = 0
    with get_pool().connection() as conn:
        users = qdb.users_for_alerts(conn)
        for u in users:
            uid, email = u["user_id"], u["email"]
            if _recent_alert(conn, uid, min_hours):
                skipped += 1
                continue
            items = collect_for_user(conn, uid)
            if not items:
                continue
            subject, body = qemail.price_drop_body(items, qauth.unsub_link(uid))
            if dry_run:
                print(f"[dry-run] {email}: {subject} ({len(items)} поз.)")
                sent += 1
                continue
            if not qemail.send(email, subject, body):
                failed += 1
                continue
            # Памʼять оновлюємо ЛИШЕ після успішної відправки — інакше збій SMTP
            # мовчки «з'їв би» сповіщення, і людина не дізналась би про зниження.
            qdb.mark_alert_sent(conn, [i for i in items if i.get("query")])
            prod_ids = [i["watchlist_id"] for i in items if not i.get("query")]
            if prod_ids:
                qdb.ack_price_drops(conn, uid, prod_ids)
            conn.commit()
            sent += 1
    return {"users": len(users), "sent": sent, "skipped_recent": skipped, "failed": failed}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Листи про зниження цін")
    ap.add_argument("--dry-run", action="store_true", help="показати, не надсилаючи")
    ap.add_argument("--min-hours", type=int, default=MIN_HOURS,
                    help="не частіше ніж раз на N годин на людину")
    a = ap.parse_args()
    r = run(dry_run=a.dry_run, min_hours=a.min_hours)
    print(f"акаунтів зі стеженням: {r['users']} · листів: {r['sent']} · "
          f"пропущено (нещодавно писали): {r['skipped_recent']} · збоїв: {r['failed']}")
    sys.exit(1 if r["failed"] else 0)
