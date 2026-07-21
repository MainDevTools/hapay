# Розгортання «Хапай» на Hetzner (bare-metal, без Docker)

> ⚠ **Написано наосліп.** У пісочниці розробки немає сервера — локально це не
> перевірялось. **Перший запуск на сервері й буде тестом.** На чистій машині це
> прийнятно; на машині з даними — ні.

**Docker відкинуто** (рішення власника, 2026-07-18: «зайвий фрагмент»). Стек стоїть
прямо на хості, керується systemd. Compose/Dockerfile видалено з репо.

## Що крутиться на CX23 (Ubuntu 24.04, IP 89.167.84.32)

| компонент | як живе | роль |
|---|---|---|
| **PostgreSQL 18** | пакет із PGDG, `postgresql.service` | база; слухає **лише localhost** |
| **API** | venv `/opt/hapay/venv`, `hapay-api.service` | uvicorn на 127.0.0.1:8080 |
| **collect** | `hapay-collect.timer` 2×/добу (05:23, 17:23) | збір цін у локальну базу |
| **Caddy** | пакет, `caddy.service` | TLS (Let's Encrypt) + проксі; єдине, що дивиться в інтернет |
| **backup** | `hapay-backup.timer` щоночі 03:17 | `pg_dump` → офсайт (`BACKUP_TARGET`) |

Postgres 18 ставиться з **PGDG-репозиторію** (Ubuntu 24.04 дає лише 16) — щоб прод
збігався з версією, проти якої зелений CI.

**Колектор живе тут** (не в GitHub Actions): база локальна й назовні не видна.
`collect.yml` в Actions більше не пише нікуди — можна вимкнути.

## Порядок (твої кроки)

1. **DNS:** A-запис `hapay.today` → `89.167.84.32` (зроблено).
2. На сервері:
   ```
   ssh root@89.167.84.32
   git clone https://github.com/MainDevTools/hapay.git /opt/hapay/repo   # якщо ще нема
   cd /opt/hapay/repo && git pull
   bash deploy/hetzner/setup.sh
   ```
   Скрипт ідемпотентний; ставить Postgres 18, створює роль/базу, venv, міграції,
   systemd-юніти, Caddy. Секрети — `/etc/hapay/hapay.env` (пароль генерує сам;
   існуючий файл не перезаписує, лише доповнює `DATABASE_URL`, якщо його нема).
3. `nano /etc/hapay/hapay.env` — перевір `HAPAY_DOMAIN`, впиши `BACKUP_TARGET`.
   **Значення не показуй CC, у git не клади.**
4. Перевірка:
   ```
   systemctl status hapay-api caddy postgresql --no-pager | grep Active
   curl -s https://hapay.today/api/health     → {"ok":true}
   ```
5. Збір разово: `systemctl start hapay-collect.service && journalctl -u hapay-collect -n 30`
6. **Бекап одразу** (коли є `BACKUP_TARGET`): `systemctl start hapay-backup.service`

## Що зроблено, щоб не повторити 17 липня (T13)

- `backup.sh` **падає**, якщо `BACKUP_TARGET` порожній — мовчазний успіх гірший за помилку.
- Дамп перевіряється: розмір + **читання назад** (`pg_restore --list`, шукає `price_snapshot`).
- Бекап їде **поза сервер**: бекап поруч із базою — один пункт відмови.
- Postgres слухає лише localhost; назовні відкриті тільки 22/80/443 (ufw).
- API працює від системного користувача `hapay` (не root).

## Раз на місяць — обов'язково

**Віднови дамп у порожню базу й порахуй рядки.** Бекап, який жодного разу не
відновлювали, — не бекап, а надія. Ми вже знаємо, скільки коштує різниця.

## Сторож збору (алерт про зупинку)

`hapay-alert.timer` кожні 15 хв питає `collect_health` і, коли збір мовчить довше за
поріг (90 хв), надсилає повідомлення — один раз на подію, з нагадуванням раз на 6 год,
поки триває. Стан живе в таблиці `ops_alert`, тож є й історія падінь.

Працює й БЕЗ каналу: фіксує стан у базі. Щоб отримувати повідомлення в Telegram:

1. створи бота в @BotFather, візьми токен;
2. `nano /etc/hapay/hapay.env` → додай `BOT_TOKEN=...`;
3. напиши щось своєму боту в Telegram;
4. `cd /opt/hapay/repo && sudo -u hapay /opt/hapay/venv/bin/python scripts/alert_collect.py --whoami`
   → покаже chat_id;
5. додай `ALERT_TG_CHAT_ID=<id>` у той самий файл;
6. `systemctl restart hapay-alert.timer`

Перевірити вручну, нічого не надсилаючи:
`cd /opt/hapay/repo && sudo -u hapay env $(cat /etc/hapay/hapay.env | xargs) /opt/hapay/venv/bin/python scripts/alert_collect.py --dry-run`
