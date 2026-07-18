#!/usr/bin/env bash
# pg_dump локальної бази ПОЗА цей сервер. Запускається systemd-таймером (hapay-backup.timer).
#
# ── Навіщо це існує ─────────────────────────────────────────────────────────────
# 2026-07-17 ми знищили історію цін: тест прочитав прод-DATABASE_URL і зробив DROP TABLE
# (T13). Append-only тригер не врятував — він боронить від UPDATE/DELETE, не від DROP.
# Історію цін НЕ МОЖНА зібрати заднім числом: учорашньої ціни вже не існує ніде.
# База — на ЦЬОМУ ж сервері (bare-metal), тож офсайт-бекап — не опція.
#
# Два правила, куплені тим днем:
#   1. Бекап на тому самому сервері, що й база, — не бекап (один пункт відмови).
#   2. Бекап, який жодного разу не відновлювали, — не бекап, а надія.
set -Eeuo pipefail

: "${DATABASE_URL:?нема DATABASE_URL (EnvironmentFile=/etc/hapay/hapay.env)}"
if [[ -z "${BACKUP_TARGET:-}" ]]; then
  echo "СТОП: BACKUP_TARGET порожній — бекапити нікуди." >&2
  echo "Мовчазний успіх тут гірший за помилку: ти думатимеш, що бекапи є." >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DUMP="$WORK/hapay-$STAMP.dump"

echo "==> pg_dump ($STAMP)"
pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-privileges --file="$DUMP"

SIZE=$(stat -c%s "$DUMP")
echo "    дамп: $(numfmt --to=iec "$SIZE")"
if (( SIZE < 1024 )); then
  echo "СТОП: дамп підозріло малий ($SIZE б). База порожня або dump зламався." >&2
  exit 1
fi

echo "==> перевірка цілісності (читаємо дамп назад)"
pg_restore --list "$DUMP" > "$WORK/toc.txt"
grep -q 'price_snapshot' "$WORK/toc.txt" || {
  echo "СТОП: у дампі нема price_snapshot — це не наша база або дамп побитий." >&2; exit 1; }
echo "    таблиць у дампі: $(grep -c 'TABLE DATA' "$WORK/toc.txt")"

echo "==> відправка → $BACKUP_TARGET"
case "$BACKUP_TARGET" in
  rsync://*|*:*)                      # Hetzner Storage Box (SSH/rsync)
    rsync -avz --remove-source-files -e "ssh -o StrictHostKeyChecking=accept-new" \
      "$DUMP" "$BACKUP_TARGET/" ;;
  s3://*)                             # Backblaze B2 / будь-який S3
    command -v rclone >/dev/null || { echo "нема rclone" >&2; exit 1; }
    rclone copy "$DUMP" "$BACKUP_TARGET" --s3-no-check-bucket ;;
  *)
    echo "СТОП: не розумію BACKUP_TARGET='$BACKUP_TARGET' (треба rsync://, host:path або s3://)" >&2
    exit 1 ;;
esac

echo "==> готово: hapay-$STAMP.dump"
echo
echo "НАГАДУВАННЯ: раз на місяць ВІДНОВИ цей дамп у порожню базу й порахуй рядки."
echo "Бекап без перевіреного відновлення — це не бекап."
