#!/usr/bin/env bash
# Bare-metal розгортання «Хапай» на Hetzner CX23 / Ubuntu 24.04. БЕЗ Docker.
#
# Стек напряму на хості: PostgreSQL 18 (PGDG) + Python-venv (uvicorn API + collector)
# + Caddy (TLS). Усе через systemd. Секрети — /etc/hapay/hapay.env (chmod 600, поза git).
#
# ⚠ ЧЕСНО: не тестовано локально (у пісочниці нема сервера). Перший запуск на сервері
#   й Є тестом. Ідемпотентний: можна ганяти повторно.
#
# Запуск (від root):
#   ssh root@<IP>
#   git clone https://github.com/MainDevTools/hapay.git /opt/hapay/repo   # якщо ще нема
#   bash /opt/hapay/repo/deploy/hetzner/setup.sh
set -Eeuo pipefail

APP_USER="hapay"
APP_DIR="/opt/hapay"
REPO_DIR="$APP_DIR/repo"
VENV="$APP_DIR/venv"
SECRET_DIR="/etc/hapay"
ENV_FILE="$SECRET_DIR/hapay.env"
PGVER=18
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mСТОП: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "запускай від root"
. /etc/os-release
[[ "${VERSION_ID:-}" == "24.04" ]] || echo "УВАГА: очікував Ubuntu 24.04, маю ${VERSION_ID:-?} — продовжую"
CODENAME="${VERSION_CODENAME:-noble}"

log "1/9 Система + базові пакети + автооновлення безпеки"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq ca-certificates curl gnupg git ufw fail2ban unattended-upgrades openssl \
  python3 python3-venv python3-pip lsb-release apt-transport-https
dpkg-reconfigure -f noninteractive unattended-upgrades

log "2/9 Фаєрвол: лише SSH + HTTPS (Postgres слухає тільки localhost, назовні не світиться)"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment 'ssh'
ufw allow 80/tcp   comment 'http -> ACME + редірект'
ufw allow 443/tcp  comment 'https'
ufw --force enable
ufw status verbose

log "3/9 SSH: лише ключі, root без пароля"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
rm -f /etc/ssh/sshd_config.d/50-cloud-init.conf
sshd -t || die "конфіг sshd зламаний — НЕ перезапускаю (втратиш доступ)"
systemctl reload ssh
systemctl enable --now fail2ban >/dev/null

log "4/9 PostgreSQL $PGVER (репозиторій PGDG — Ubuntu має лише 16 за замовч.)"
if ! psql --version 2>/dev/null | grep -q " $PGVER\."; then
  install -d /usr/share/keyrings
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg
  echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt ${CODENAME}-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
  apt-get update -qq
  apt-get install -y -qq "postgresql-$PGVER"
fi
systemctl enable --now postgresql
sudo -u postgres psql -tAc 'SELECT version()' | head -1

log "5/9 Секрети → $ENV_FILE (пароль Postgres генерується сам, chmod 600)"
install -d -m 0700 "$SECRET_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  PGPASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
  cat > "$ENV_FILE" <<EOF
# Секрети «Хапай». НІКОЛИ не комітити (git-безпека §8). chmod 600.
POSTGRES_USER=hapay
POSTGRES_PASSWORD=$PGPASS
POSTGRES_DB=hapay
# Локальний Postgres — застосунок ходить через localhost:
DATABASE_URL=postgresql://hapay:$PGPASS@localhost:5432/hapay

# Домен для HTTPS (Caddy бере сертифікат саме на нього):
HAPAY_DOMAIN=hapay.today

# Куди складати pg_dump ПОЗА цей сервер (host:path / rsync:// / s3://).
# Порожнє = бекапів НЕМА і hapay-backup впаде навмисно (мовчазний успіх гірший за помилку).
BACKUP_TARGET=

# Опційно (Telegram Mini App):
BOT_TOKEN=
EOF
  chmod 600 "$ENV_FILE"
  echo "СТВОРЕНО з готовим паролем. Перевір домен і впиши BACKUP_TARGET: nano $ENV_FILE"
else
  echo "вже існує — не чіпаю (пароль не перегенеровую)"
  # env від Docker-версії не мав DATABASE_URL (його будував compose) — доповнюємо
  if ! grep -q '^DATABASE_URL=' "$ENV_FILE"; then
    set -a; . "$ENV_FILE"; set +a
    echo "DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB}" >> "$ENV_FILE"
    echo "  додано DATABASE_URL (bare-metal, localhost)"
  fi
fi
set -a; . "$ENV_FILE"; set +a

log "6/9 Роль і база в Postgres (ідемпотентно)"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$POSTGRES_USER'" | grep -q 1 \
  || sudo -u postgres psql -qc "CREATE ROLE $POSTGRES_USER LOGIN PASSWORD '$POSTGRES_PASSWORD'"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$POSTGRES_DB'" | grep -q 1 \
  || sudo -u postgres createdb -O "$POSTGRES_USER" "$POSTGRES_DB"

log "7/9 Код + Python-venv + міграції"
[[ -d "$REPO_DIR/.git" ]] || die "нема $REPO_DIR — спершу: git clone https://github.com/MainDevTools/hapay.git $REPO_DIR"
# репо належить користувачу hapay, а git pull робиться від root — без цього git відмовляє
# з «dubious ownership» і оновлення мовчки не доїжджають
git config --global --add safe.directory "$REPO_DIR" 2>/dev/null || true
if ! id -u "$APP_USER" &>/dev/null; then
  adduser --system --group --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
sudo -u "$APP_USER" env DATABASE_URL="$DATABASE_URL" "$VENV/bin/python" -m db.migrate

log "8/9 systemd: API (uvicorn на 127.0.0.1:8080)"
cat > /etc/systemd/system/hapay-api.service <<EOF
[Unit]
Description=Хапай API (uvicorn)
After=network.target postgresql.service
Requires=postgresql.service
[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/uvicorn api.main:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

# колектор 2x/добу
cat > /etc/systemd/system/hapay-collect.service <<EOF
[Unit]
Description=Хапай — збір цін
After=postgresql.service
[Service]
Type=oneshot
User=$APP_USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/python -m collect
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

# бекап щоночі (pg_dump напряму — база локальна)
install -m 0755 "$REPO_DIR/deploy/hetzner/backup.sh" /usr/local/bin/hapay-backup
cat > /etc/systemd/system/hapay-backup.service <<EOF
[Unit]
Description=Хапай — pg_dump бази ПОЗА цей сервер
After=postgresql.service
[Service]
Type=oneshot
EnvironmentFile=$ENV_FILE
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
systemctl enable --now hapay-api.service
systemctl enable hapay-collect.timer hapay-backup.timer

log "9/9 Caddy (TLS + зворотний проксі на 127.0.0.1:8080)"
if ! command -v caddy &>/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi
install -m 0644 "$REPO_DIR/deploy/hetzner/Caddyfile" /etc/caddy/Caddyfile
# Caddy бачить ЛИШЕ домен, не весь hapay.env: пароль БД йому не потрібен, а systemd
# при падінні друкує оточення сервісу в journald — секретам там не місце.
grep '^HAPAY_DOMAIN=' "$ENV_FILE" > /etc/hapay/caddy.env
chmod 644 /etc/hapay/caddy.env
install -d /etc/systemd/system/caddy.service.d
cat > /etc/systemd/system/caddy.service.d/hapay.conf <<'EOF'
[Service]
EnvironmentFile=/etc/hapay/caddy.env
EOF
systemctl daemon-reload
systemctl enable caddy
systemctl restart caddy

IP="$(curl -fsS https://ipv4.icanhazip.com 2>/dev/null || echo '<IP>')"
cat <<EOF

╭──────────────────────────────────────────────────────────────────╮
│  Готово (bare-metal, без Docker). ПЕРЕВІР:                        │
╰──────────────────────────────────────────────────────────────────╯
  systemctl status hapay-api caddy postgresql --no-pager | grep Active
  curl -s https://hapay.today/api/health          → {"ok":true}
  Збір разово:  sudo -u $APP_USER env \$(grep -v '^#' $ENV_FILE|xargs) $VENV/bin/python -m collect
                (або: systemctl start hapay-collect.service)
  Бекап ОДРАЗУ (коли впишеш BACKUP_TARGET): systemctl start hapay-backup.service
  Логи API:     journalctl -u hapay-api -n 50 --no-pager
  DNS: A hapay.today → $IP
EOF
