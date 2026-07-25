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

**E1 (сервер) — ЗРОБЛЕНО 2026-07-25, у проді.** Міграція 0169 (email_verified +
account_token з code_hash/TTL/одноразовістю). auth.py (make_code/hash_code), email.py
(smtplib-env | LogSender, ніколи не кидає), db.py (create/consume_token,
set_email_verified, update_password — гасить reset-токени). 4 ендпойнти + register/
login/me правки; rate-limit email 5/год, code 10/10хв. **Живий smoke наскрізь:**
register→verified:false, код із журналу→verify→true, /me→true, reset→новий пароль
(**login новим 200, старим 401**), reset-код мертвий після зміни. Тести: token/email
юніт 5/5 + test_api round-trip (одноразовість/протухання/no-enumeration/старий пароль
мертвий) + dbguard; **CI зелений**.

**E2 (MAUI) — ЗРОБЛЕНО 2026-07-25** (код + збірка 0 errors + прогін на емуляторі):
AuthService (EmailVerified у SecureStorage + VerifyEmail/ResendVerify), ApiService
(4 методи), профіль-банер «Email не підтверджено» (діалог коду + resend),
ResetPasswordPage (двоетапний «забув пароль»), «Забув пароль?» на вході.
**Візуально підтверджено:** login з «Забув пароль?», реєстрація, банер верифікації
в профілі (бурштиновий, кнопки «Ввести код»/«Надіслати код») — усе рендериться.
«Забув пароль?» правильно ховається в режимі реєстрації.

**Канал — ПІДКЛЮЧЕНО 2026-07-25 (Resend SMTP).** Живий тест: reset/request на
maindevtools@gmail.com → лист реально прийшов у Gmail. env на сервері:
SMTP_HOST=smtp.resend.com, **SMTP_PORT=587** (⚠ НЕ 465 — Hetzner блокує вихідні
465/25, буде TimeoutError; 587/2465/2587 відкриті), SMTP_USER=resend, SMTP_PASS=re_-ключ,
SMTP_FROM=onboarding@resend.dev.

**Домен ПІДКЛЮЧЕНО 2026-07-25.** hapay.today верифіковано в Resend (DKIM
resend._domainkey + SPF/MX на send.hapay.today + DMARC _dmarc — усі в HostPro DNS,
поширились на всі 4 NS). SMTP_FROM=noreply@hapay.today; Resend прийняв лист із нашого
домену (автентифікований DKIM/SPF/DMARC → inbox, не спам). Канал повністю робочий для
БУДЬ-ЯКИХ адрес. Дорогою: Hetzner блокує 465 → порт 587; ns3 HostPro відставав ~пів
години (наздогнав сам).

**Лишилось (🧭 оператор, дрібне):**
- **Рев'ю текстів листів** (api/email.py verify_body/reset_body) — юр-дотичне,
  фактологічний тон витриманий, але фінальне слово оператора.
- DMARC p=none (лише моніторинг) — з часом можна посилити до quarantine/reject.

**S13 ПОВНІСТЮ ЗАКРИТО:** E1 сервер + E2 MAUI + реальний email-канал через власний домен.
