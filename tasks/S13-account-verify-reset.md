# Задача S13 — Верифікація email + скидання пароля («нормальна реєстрація»)

**Роль:** Виконавець · **Автор:** Диригент, 2026-07-25 · **Статус:** `E1 в роботі`
**Залежності:** S11 (auth: app_user, JWT, pbkdf2), rate-limiter (bug-review), email-канал (🧭).
**Рішення оператора 2026-07-25:** обсяг = верифікація + скидання пароля; провайдер = SES/Brevo (обидва SMTP).

### 0. Навіщо
Зараз реєстрація одразу видає JWT без підтвердження email, а забутий пароль = втрачений
акаунт назавжди. Додаємо: (1) підтвердження email, (2) «забув пароль».

### 1. Ключові рішення (зафіксовані)
- **Soft-verify:** register ВИДАЄ JWT одразу (вхід не блокуємо — акаунт дає лише
  watchlist, hard-verify створив би тертя на рівному місці). `email_verified=false`,
  лист надіслано; профіль показує статус + «підтвердити». Hard-gate — окреме 🧭 пізніше.
- **КОД, не лінк:** 6-значний числовий код у листі (звичний UX, без deep-linking у MAUI).
  Захист від перебору: TTL + одноразовість + прив'язка (verify→user, reset→email) +
  rate-limit на спроби вводу.
- **Хеш токена в БД:** зберігаємо `sha256(code)`, не сам код — витік БД ≠ активні токени
  (та сама логіка, що пароль ніколи не plaintext).
- **SMTP-абстракція (stdlib):** `smtplib` через env (SMTP_HOST/PORT/USER/PASS/FROM/TLS) —
  працює з SES/Brevo/будь-яким. БЕЗ env → LogSender (пише код у journal, dev-режим,
  НЕ падає). Реальний канал = лише env, без зміни коду (принцип alert_collect).
- **Reset не розкриває існування email:** `/reset/request` завжди 200 (проти enumeration).
- **TTL:** verify 24 год, reset 1 год. Rate-limit: resend/reset-request (per-IP+email),
  verify/reset-confirm (per-IP, проти перебору коду).

### 2. Схема (0169)
```sql
app_user += email_verified BOOLEAN NOT NULL DEFAULT false
account_token(token_id, user_id FK, kind 'verify'|'reset', code_hash TEXT,
              expires_at, used_at, created_at)   -- code_hash = sha256(код); одноразовий
```

### 3. Ендпойнти
- `register` (є) → +email_verified=false, згенерувати verify-код, надіслати, JWT як і зараз.
- `POST /api/auth/verify` {code} (auth) → consume → email_verified=true.
- `POST /api/auth/verify/resend` (auth, rate-limit) → новий код + лист.
- `POST /api/auth/reset/request` {email} (rate-limit) → код, лист; ЗАВЖДИ 200.
- `POST /api/auth/reset/confirm` {email, code, new_password} (rate-limit) → consume → новий hash.
- `/api/me` → +email_verified.

### 4. Definition of Done
- [ ] `auth.py`: `make_code`/`hash_code` (secrets, sha256); TTL-константи.
- [ ] `api/email.py`: `send(to, subject, body)` — smtplib(env) | LogSender; ніколи не падає.
- [ ] `db.py`: create_token / consume_token (атомарно: не-used+не-expired → used) /
      set_email_verified / update_password; get_user += email_verified.
- [ ] main.py: 4 нові ендпойнти + register/me правки; rate-limit на надсилання й перебір.
- [ ] Тести: token round-trip (consume одноразовий/протухлий/чужий), reset-no-enumeration,
      email LogSender, rate-limit на коди; test_api інтеграція.
- [ ] MAUI (E2): банер «email не підтверджено» + екран коду; «Забув пароль» на вході.

### 5. Guardrails
- Код у БД лише як хеш; лист — єдине місце plaintext-коду.
- Пароль-хешування без змін (pbkdf2 600k). Зміна пароля інвалідує всі reset-токени юзера.
- Email-канал необов'язковий для роботи коду (LogSender) — реліз без нього НЕ блокується,
  але верифікація тоді «сліпа» (код лише в журналі сервера). Реальний SMTP — перед публічним релізом.
- DKIM/SPF/DMARC на hapay.today — 🧭 оператор (інакше листи в спам). Поза кодом.

---
## Outcome (Виконавець)
_(заповнюється під час E1/E2)_
