# Деплой «Радара знижок»

Три незалежні частини (кожну вмикаєш коли готовий; конвеєр чекає):

## 0. БД — PostgreSQL 16 (Neon, free-forever)
Схема `0001` — **чистий PostgreSQL** (Timescale не потрібен; hypertable/cagg/компресія — майбутній `0002` scale-upgrade). Тому підходить **Neon** (безкоштовно назавжди).

**Neon (рекомендовано, $0):**
1. **console.neon.tech** → Sign up → **Create project** (регіон **EU — Frankfurt**, ближче до України).
2. Дашборд → **Connection string** → скопіюй (формат `postgresql://user:pass@ep-...neon.tech/dbname?sslmode=require`).
   - `sslmode=require` уже в рядку Neon — залиш.
   - Бери **звичайний** (не «pooled») рядок для колектора: міграції роблять DDL.
3. Це **секрет** `DATABASE_URL` — ніколи в репо/чат (тільки Actions/Fly secrets).

*(Альтернативи: self-host Postgres на VPS (~$5/міс) або Timescale Cloud trial. Для Neon схема вже готова — нічого не переписувати.)*

## 1. Колектор (Шар 1) — GitHub Actions, БЕЗ хостингу
Уже налаштований (`.github/workflows/collect.yml`, 2×/добу).
- Репо → **Settings → Secrets and variables → Actions → New secret**: `DATABASE_URL`.
- Перший прогін: **Actions → collect → Run workflow** (застосує `0001` сам).
- Далі пише ціни Pethouse автоматично → за ~30 днів реальні verified-бейджі.

## 2. read-API + Mini App (Шар 3) — потрібен хост

### Fly.io
```bash
flyctl launch --no-deploy          # підхопить Dockerfile + fly.toml (зміни app-назву)
flyctl secrets set DATABASE_URL="postgresql://…"   BOT_TOKEN="123:abc"
flyctl secrets set RUN_MIGRATIONS=1                 # опц.: застосувати 0001 на старті
flyctl deploy
```
Здоров'я: `https://<app>.fly.dev/api/health` → `{"ok":true}`. Mini App: `https://<app>.fly.dev/`.

### Railway (альтернатива)
Connect repo → Railway візьме `Dockerfile` → додай змінні `DATABASE_URL`, `BOT_TOKEN`,
`PORT=8080`. Деплой автоматично.

## 3. Telegram-бот + Mini App
1. @BotFather → `/newbot` → отримай **токен** → поклади як секрет `BOT_TOKEN` (крок 2).
2. @BotFather → `/newapp` (або bot → Configure Mini App) → **Web App URL** = `https://<app>.fly.dev/`.
3. Користувач: `/start` → кнопка Mini App → вітрина.

## Перевірка «наживо»
- `/api/health` → `{"ok":true}`; `/api/discounts` → JSON знижок (після collect-прогону).
- Mini App відкривається в Telegram, показує картки з бейджами.

> Секрети (`DATABASE_URL`, `BOT_TOKEN`) — лише у сховищах платформ (Actions secrets / Fly secrets),
> **ніколи в git** (`workflow/07-conventions.md`).
