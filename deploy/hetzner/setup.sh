#!/usr/bin/env bash
# Разове налаштування чистого Hetzner CX22 / Ubuntu 24.04 під «Радар знижок».
#
# ⚠ ЧЕСНО: написано наосліп. У пісочниці розробки немає ні Docker, ні WSL, ні Postgres,
#   тож локально це не перевірялось. ПЕРШИЙ ЗАПУСК НА СЕРВЕРІ Й Є ТЕСТОМ. На чистій
#   машині втрачати нічого, але не запускай це на сервері з даними.
#
# Ідемпотентний: можна ганяти повторно.
#
# Запуск (від root, одразу після створення сервера):
#   ssh root@<IP>
#   curl -fsSL https://raw.githubusercontent.com/<OWNER>/radar-znyzhok/main/deploy/hetzner/setup.sh -o setup.sh
#   less setup.sh          # ПРОЧИТАЙ, перш ніж виконувати чужий скрипт від root
#   bash setup.sh
set -Eeuo pipefail

RADAR_USER="radar"
RADAR_DIR="/opt/radar"
SECRET_DIR="/etc/radar"
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mСТОП: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "запускай від root"
[[ -f /etc/os-release ]] && . /etc/os-release
[[ "${VERSION_ID:-}" == "24.04" ]] || echo "УВАГА: очікував Ubuntu 24.04, маю ${VERSION_ID:-?} — продовжую"

log "1/8 Оновлення системи + автооновлення безпеки"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq ca-certificates curl gnupg ufw fail2ban unattended-upgrades postgresql-client-16
# без цього сервер тихо гниє незакритими дірками
dpkg-reconfigure -f noninteractive unattended-upgrades

log "2/8 Користувач ${RADAR_USER} (працюємо не від root)"
if ! id -u "$RADAR_USER" &>/dev/null; then
  adduser --system --group --home "$RADAR_DIR" --shell /usr/sbin/nologin "$RADAR_USER"
fi
install -d -o "$RADAR_USER" -g "$RADAR_USER" -m 0750 "$RADAR_DIR"

log "3/8 Фаєрвол: закрито все, крім SSH і HTTPS"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment 'ssh'
ufw allow 80/tcp   comment 'http -> редірект + ACME'
ufw allow 443/tcp  comment 'https'
ufw --force enable
ufw status verbose

log "4/8 SSH: лише ключі, root без пароля"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
# Hetzner кладе свої налаштування сюди — вони перекривають головний файл
rm -f /etc/ssh/sshd_config.d/50-cloud-init.conf
sshd -t || die "конфіг sshd зламаний — НЕ перезапускаю, бо втратиш доступ"
systemctl reload ssh
systemctl enable --now fail2ban

log "5/8 Docker"
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

log "6/8 Секрети → ${SECRET_DIR}/radar.env (поза git, chmod 600)"
install -d -m 0700 "$SECRET_DIR"
if [[ ! -f "$SECRET_DIR/radar.env" ]]; then
  cat > "$SECRET_DIR/radar.env" <<'EOF'
# Секрети. НІКОЛИ не комітити (git-безпека §8). chmod 600.
DATABASE_URL=postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
BOT_TOKEN=
RADAR_DOMAIN=radar.example.com
GHCR_OWNER=
# Куди складати pg_dump ПОЗА цим сервером (Storage Box / B2). Порожнє = бекапів нема.
BACKUP_TARGET=
EOF
  chmod 600 "$SECRET_DIR/radar.env"
  echo "СТВОРЕНО шаблон — впиши значення РУКАМИ: nano $SECRET_DIR/radar.env"
else
  echo "вже існує — не чіпаю"
fi

log "7/8 Код у ${RADAR_DIR}"
if [[ ! -d "$RADAR_DIR/repo/.git" ]]; then
  echo "Клонуй репо вручну (щоб не зашивати сюди URL нового акаунта):"
  echo "  git clone https://github.com/<OWNER>/radar-znyzhok.git $RADAR_DIR/repo"
fi

log "8/8 Бекапи + таймер"
install -m 0755 "$RADAR_DIR/repo/deploy/hetzner/backup.sh" /usr/local/bin/radar-backup 2>/dev/null \
  || echo "backup.sh ще нема (репо не склоновано) — постав пізніше"
cat > /etc/systemd/system/radar-backup.service <<EOF
[Unit]
Description=Радар — pg_dump бази ПОЗА цей сервер
[Service]
Type=oneshot
EnvironmentFile=$SECRET_DIR/radar.env
ExecStart=/usr/local/bin/radar-backup
EOF
cat > /etc/systemd/system/radar-backup.timer <<'EOF'
[Unit]
Description=Радар — бекап щодня о 03:17
[Timer]
OnCalendar=*-*-* 03:17:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable radar-backup.timer 2>/dev/null || true

cat <<EOF

╭──────────────────────────────────────────────────────────────────╮
│  Базове налаштування завершено. ЩО ЗАЛИШИЛОСЬ ЗРОБИТИ РУКАМИ:    │
╰──────────────────────────────────────────────────────────────────╯
  1. nano $SECRET_DIR/radar.env        — вписати DATABASE_URL, домен, GHCR_OWNER
  2. git clone <репо> $RADAR_DIR/repo
  3. DNS: A-запис домену → $(curl -fsS https://ipv4.icanhazip.com 2>/dev/null || echo '<IP>')
     Тільки ПІСЛЯ цього піднімай Caddy — інакше Let's Encrypt дасть по руках
     за невдалі спроби (є ліміт).
  4. cd $RADAR_DIR/repo/deploy/hetzner && docker compose --env-file $SECRET_DIR/radar.env up -d
  5. systemctl start radar-backup.service && journalctl -u radar-backup -n 30
     ↑ перевір бекап ОДРАЗУ. Бекап, який не пробували відновити, — не бекап.
EOF
