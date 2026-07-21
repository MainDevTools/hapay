#!/usr/bin/env bash
# Один деплой «Хапая» на сервері: git pull → міграції → рестарт API — у ПРАВИЛЬНОМУ порядку.
#
# Навіщо: 2026-07-19 забули накотити 0003 після git pull — auth не працював, поки не
# запустили міграцію вручну. Міграцію легко пропустити; тут вона обов'язкова й перша
# після коду. Порядок критичний: код → схема → рестарт (інакше API стартує на старій схемі).
#
# Запуск (від root): bash /opt/hapay/repo/deploy/hetzner/deploy.sh
set -Eeuo pipefail

REPO_DIR="/opt/hapay/repo"
ENV_FILE="/etc/hapay/hapay.env"
VENV="/opt/hapay/venv"
APP_USER="hapay"
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mСТОП: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "запускай від root"
[[ -f "$ENV_FILE" ]] || die "нема $ENV_FILE"
[[ -d "$REPO_DIR/.git" ]] || die "нема $REPO_DIR"

log "1/5 git pull"
git config --global --add safe.directory "$REPO_DIR" 2>/dev/null || true
BEFORE=$(git -C "$REPO_DIR" rev-parse --short HEAD)
SELF="$REPO_DIR/deploy/hetzner/deploy.sh"
SELF_BEFORE=$(sha256sum "$SELF" | cut -d' ' -f1)
git -C "$REPO_DIR" pull --ff-only
AFTER=$(git -C "$REPO_DIR" rev-parse --short HEAD)
echo "    $BEFORE → $AFTER"

# ── Деплой мусить уміти оновити САМ СЕБЕ ──────────────────────────────────────────
# 2026-07-21: у deploy.sh додали встановлення сторожа-таймера, деплой пройшов
# «успішно» — а таймера не з'явилось. Bash читає скрипт із диска ПО ХОДУ виконання,
# тож `git pull` підмінив файл, але поточний запуск доїхав на старому тексті. Гірше:
# зміна довжини файла під час виконання може змусити bash продовжити з випадкового
# зміщення й виконати сміття.
#
# Тому: якщо pull змінив цей файл — перезапускаємо СЕБЕ новим, один раз (прапорець
# проти нескінченного циклу).
if [[ "$(sha256sum "$SELF" | cut -d' ' -f1)" != "$SELF_BEFORE" && -z "${DEPLOY_SELF_UPDATED:-}" ]]; then
    log "deploy.sh оновився — перезапускаю новим"
    DEPLOY_SELF_UPDATED=1 exec bash "$SELF" "$@"
fi

log "2/5 оновлення Python-залежностей (якщо requirements змінились)"
"$VENV/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

log "3/5 міграції БД (форвардні; вже накочені пропускаються)"
set -a; . "$ENV_FILE"; set +a
: "${DATABASE_URL:?нема DATABASE_URL у $ENV_FILE}"
cd "$REPO_DIR"
APPLIED=$(sudo -u "$APP_USER" env DATABASE_URL="$DATABASE_URL" "$VENV/bin/python" -m db.migrate)
echo "    $APPLIED"

log "4/5 рестарт API + сторож збору"
systemctl restart hapay-api

# Сторож збору (systemd-таймер). Ставимо ТУТ, а не лише в setup.sh: setup виконують
# раз, а нові юніти мають доїжджати звичайним деплоєм. Ідемпотентно — просто
# перезаписуємо файли й перезавантажуємо systemd.
install -m 644 "$REPO_DIR/deploy/hetzner/systemd/hapay-alert.service" /etc/systemd/system/
install -m 644 "$REPO_DIR/deploy/hetzner/systemd/hapay-alert.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hapay-alert.timer >/dev/null
echo "    сторож: $(systemctl is-active hapay-alert.timer)"

log "5/5 health-перевірка (локально, повз Caddy)"
ok=0
for i in $(seq 1 15); do
  if curl -fsS http://127.0.0.1:8080/api/health 2>/dev/null | grep -q '"ok":true'; then ok=1; break; fi
  sleep 1
done
if [[ "$ok" == 1 ]]; then
  echo "    API живий ✓"
else
  die "API не відповідає після рестарту — дивись: journalctl -u hapay-api -n 50"
fi

echo
echo "Деплой завершено: $BEFORE → $AFTER"
