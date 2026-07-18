#!/usr/bin/env bash
# Разове налаштування чистого Hetzner CX23 / Ubuntu 24.04 під «Хапай».
#
# ⚠ ЧЕСНО: написано наосліп. У пісочниці розробки немає ні Docker, ні WSL, ні Postgres,
#   тож локально це не перевірялось. ПЕРШИЙ ЗАПУСК НА СЕРВЕРІ Й Є ТЕСТОМ. На чистій
#   машині втрачати нічого, але не запускай це на сервері з даними.
#
# Архітектура (2026-07-18): усе на одному сервері — db (Postgres) + api + caddy + collect.
# Neon відкинуто; колектор переїхав сюди з GitHub Actions (база приватна).
#
# Ідемпотентний: можна ганяти повторно.
#
# Запуск (від root, одразу після створення сервера):
#   ssh root@<IP>
#   curl -fsSL https://raw.githubusercontent.com/MainDevTools/hapay/main/deploy/hetzner/setup.sh -o setup.sh
#   less setup.sh          # ПРОЧИТАЙ, перш ніж виконувати чужий скрипт від root
#   bash setup.sh
set -Eeuo pipefail

APP_USER="hapay"
APP_DIR="/opt/hapay"
REPO_DIR="$APP_DIR/repo"
SECRET_DIR="/etc/hapay"
ENV_FILE="$SECRET_DIR/hapay.env"
COMPOSE_DIR="$REPO_DIR/deploy/hetzner"
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mСТОП: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "запускай від root"
[[ -f /etc/os-release ]] && . /etc/os-release
[[ "${VERSION_ID:-}" == "24.04" ]] || echo "УВАГА: очікував Ubuntu 24.04, маю ${VERSION_ID:-?} — продовжую"

log "1/7 Оновлення системи + автооновлення безпеки"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq ca-certificates curl gnupg git ufw fail2ban unattended-upgrades openssl
# без цього сервер тихо гниє незакритими дірками
dpkg-reconfigure -f noninteractive unattended-upgrades

log "2/7 Фаєрвол: закрито все, крім SSH і HTTPS (Postgres назовні НЕ світиться)"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment 'ssh'
ufw allow 80/tcp   comment 'http -> редірект + ACME'
ufw allow 443/tcp  comment 'https'
ufw --force enable
ufw status verbose

log "3/7 SSH: лише ключі, root без пароля"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
rm -f /etc/ssh/sshd_config.d/50-cloud-init.conf   # Hetzner кладе тут перекриття
sshd -t || die "конфіг sshd зламаний — НЕ перезапускаю, бо втратиш доступ"
systemctl reload ssh
systemctl enable --now fail2ban

log "4/7 Docker"
if ! command -v docker &>/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
docker --version

log "5/7 Секрети → $ENV_FILE (поза git, chmod 600; пароль Postgres генерується сам)"
install -d -m 0700 "$SECRET_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  PGPASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"   # URL-safe, без /+=
  cat > "$ENV_FILE" <<EOF
# Секрети «Хапай». НІКОЛИ не комітити (git-безпека §8). chmod 600.
# Postgres — на цьому ж сервері; DATABASE_URL compose будує сам із цих трьох:
POSTGRES_USER=hapay
POSTGRES_PASSWORD=$PGPASS
POSTGRES_DB=hapay

# Домен для HTTPS (Caddy отримає сертифікат саме на нього):
HAPAY_DOMAIN=hapay.today

# Куди складати pg_dump ПОЗА цей сервер (Storage Box: user@host:path / rsync:// / s3://).
# Порожнє = бекапів НЕМА і hapay-backup впаде навмисно (мовчазний успіх гірший за помилку).
BACKUP_TARGET=

# Опційно (Telegram Mini App):
BOT_TOKEN=
EOF
  chmod 600 "$ENV_FILE"
  echo "СТВОРЕНО з готовим паролем Postgres. Перевір/впиши домен і BACKUP_TARGET: nano $ENV_FILE"
else
  echo "вже існує — не чіпаю (пароль не перегенеровую)"
fi

log "6/7 Код у $REPO_DIR"
install -d "$APP_DIR"
if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "Репо ще не склоновано. Зроби вручну (URL — твого GitHub-акаунта):"
  echo "  git clone https://github.com/MainDevTools/hapay.git $REPO_DIR"
  echo "Тоді запусти setup.sh ще раз — доставить таймери."
else
  log "7/7 Таймери: колектор 2x/добу + бекап щоночі"
  # колектор
  cat > /etc/systemd/system/hapay-collect.service <<EOF
[Unit]
Description=Хапай — збір цін (collect)
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
WorkingDirectory=$COMPOSE_DIR
ExecStart=/usr/bin/docker compose --env-file $ENV_FILE run --rm collect
EOF
  cat > /etc/systemd/system/hapay-collect.timer <<'EOF'
[Unit]
Description=Хапай — збір 2x/добу
[Timer]
OnCalendar=*-*-* 05:23:00
OnCalendar=*-*-* 17:23:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
  # бекап (backup.sh сам читає ENV_FILE і робить dump через контейнер)
  install -m 0755 "$COMPOSE_DIR/backup.sh" /usr/local/bin/hapay-backup
  cat > /etc/systemd/system/hapay-backup.service <<EOF
[Unit]
Description=Хапай — pg_dump бази ПОЗА цей сервер
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
WorkingDirectory=$COMPOSE_DIR
ExecStart=/usr/local/bin/hapay-backup
EOF
  cat > /etc/systemd/system/hapay-backup.timer <<'EOF'
[Unit]
Description=Хапай — бекап щодня о 03:17
[Timer]
OnCalendar=*-*-* 03:17:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable hapay-collect.timer hapay-backup.timer
  echo "таймери увімкнено (стартують за розкладом)"
fi

IP="$(curl -fsS https://ipv4.icanhazip.com 2>/dev/null || echo '<IP>')"
cat <<EOF

╭──────────────────────────────────────────────────────────────────╮
│  Готово. ЩО ЗАЛИШИЛОСЬ ЗРОБИТИ РУКАМИ:                            │
╰──────────────────────────────────────────────────────────────────╯
  1. nano $ENV_FILE          — перевір HAPAY_DOMAIN, впиши BACKUP_TARGET
  2. git clone <репо> $REPO_DIR   (якщо ще не зроблено) → потім `bash setup.sh` ще раз
  3. DNS: A-запис hapay.today → $IP
     Тільки ПІСЛЯ цього піднімай Caddy — у Let's Encrypt є ліміт невдалих спроб.
  4. cd $COMPOSE_DIR && docker compose --env-file $ENV_FILE up -d --build
     ↑ підніме db + migrate(одноразово) + api + caddy. Перший build ~2-3 хв.
  5. Перевір: curl -s https://hapay.today/api/health   → {"ok":true}
  6. Збір разово: docker compose --env-file $ENV_FILE run --rm collect
  7. Бекап ОДРАЗУ: systemctl start hapay-backup.service && journalctl -u hapay-backup -n 40
     Бекап, який не пробували, — не бекап.
EOF
