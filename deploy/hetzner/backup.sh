#!/usr/bin/env bash
# pg_dump бази ПОЗА цей сервер. Запускається systemd-таймером (hapay-backup.timer).
#
# ── Навіщо це існує ─────────────────────────────────────────────────────────────
# 2026-07-17 ми знищили історію цін: тест прочитав прод-DATABASE_URL і зробив DROP TABLE
# (T13). Append-only тригер не врятував — він боронить від UPDATE/DELETE, не від DROP.
# Історію цін НЕ МОЖНА зібрати заднім числом: учорашньої ціни вже не існує ніде.
# А тепер база — на ЦЬОМУ ж сервері (Neon відкинуто), тож офсайт-бекап — не опція.
#
# Два правила, куплені тим днем:
#   1. Бекап на тому самому сервері, що й база, — не бекап (один пункт відмови).
#   2. Бекап, який жодного разу не відновлювали, — не бекап, а надія.
#
# Postgres не має публічного порту → дамп робимо ЧЕРЕЗ контейнер (`compose exec db`),
# а не хостовим pg_dump. Версія pg_dump усередині завжди збігається з базою.
set -Eeuo pipefail

ENV_FILE="${HAPAY_ENV:-/etc/hapay/hapay.env}"
COMPOSE_DIR="${HAPAY_COMPOSE_DIR:-/opt/hapay/repo/deploy/hetzner}"
[[ -f "$ENV_FILE" ]] || { echo "СТОП: нема $ENV_FILE" >&2; exit 1; }
# POSTGRES_USER / POSTGRES_DB / BACKUP_TARGET
set -a; . "$ENV_FILE"; set +a
: "${POSTGRES_USER:?нема POSTGRES_USER у $ENV_FILE}"
: "${POSTGRES_DB:?нема POSTGRES_DB у $ENV_FILE}"

if [[ -z "${BACKUP_TARGET:-}" ]]; then
  echo "СТОП: BACKUP_TARGET порожній — бекапити нікуди." >&2
  echo "Мовчазний успіх тут гірший за помилку: ти думатимеш, що бекапи є." >&2
  exit 1
fi

dc() { docker compose --env-file "$ENV_FILE" "$@"; }
cd "$COMPOSE_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DUMP="$WORK/hapay-$STAMP.dump"

echo "==> pg_dump через контейнер ($STAMP)"
# -Fc: стиснутий формат + вибіркове відновлення через pg_restore. -T: без TTY (для пайпа).
dc exec -T db pg_dump -U "$POSTGRES_USER" --format=custom --no-owner --no-privileges \
  "$POSTGRES_DB" > "$DUMP"

SIZE=$(stat -c%s "$DUMP")
echo "    дамп: $(numfmt --to=iec "$SIZE")"

# Порожній дамп = мовчазна катастрофа: ти «бекапиш» щодня, а всередині нічого.
if (( SIZE < 1024 )); then
  echo "СТОП: дамп підозріло малий ($SIZE б). База порожня або dump зламався." >&2
  exit 1
fi

# 1) магія формату: кастомний дамп починається з байтів PGDMP
head -c5 "$DUMP" | grep -q 'PGDMP' || {
  echo "СТОП: дамп не схожий на pg_dump custom (нема PGDMP на початку)." >&2; exit 1; }

# 2) вміст: читаємо назад ЧЕРЕЗ контейнер (версія pg_restore = версія бази) і шукаємо нашу таблицю
echo "==> перевірка цілісності (читаємо дамп назад)"
if dc exec -T db pg_restore --list < "$DUMP" | grep -q 'price_snapshot'; then
  echo "    price_snapshot знайдено — дамп валідний"
else
  echo "СТОП: у дампі нема price_snapshot — це не наша база або дамп побитий." >&2
  exit 1
fi

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
