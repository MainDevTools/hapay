# Задача S15 — Адмін-функції під ролями (керування акаунтами, зміна ролей, метрики)

**Роль:** Виконавець · **Автор:** Диригент, 2026-07-25 · **Статус:** `E1 в роботі`
**Залежності:** S11 (app_user.role — user/collector/moderator/admin уже в схемі), S13 (email_verified).
**Рішення оператора 2026-07-25:** гість = неавторизований (не роль); ролі та права нижче.

### 0. Навіщо
Ролі в БД є (S11), але порожні — жодної адмін-дії. Додаємо ФУНКЦІЇ, що дають їм сенс.

### 1. Ролі й права (фінал)
| Роль | Права |
|---|---|
| guest | каталог/стрічка (неавторизований — уже є, НЕ роль у БД) |
| user | + watchlist/стеження |
| collector | + збір цін (технічна, ортогональна — вже є) |
| moderator | + керування акаунтами + метрики (НЕ змінює ролі) |
| admin | + зміна ролей іншим (єдина відмінність від moderator) |

### 2. Схема (0170)
```sql
app_user += is_active BOOLEAN NOT NULL DEFAULT true   -- бан = false; login відхиляє
admin_audit(id, actor_id, action, target_id, detail, created_at)  -- хто/що/кому/коли
```

### 3. Гейти (main.py)
- `require_moderator` — role ∈ {moderator, admin}.
- `require_admin` — role = admin.

### 4. Ендпойнти (усі під гейтом + аудит змін)
- `GET  /api/admin/users` (moderator+) — список: email, role, is_active, verified, created, watchlist_n.
- `GET  /api/admin/metrics` (moderator+) — к-сть юзерів по ролях, verified-частка, стан збору (freshness/queue).
- `POST /api/admin/users/{id}/role` (**admin**) — {role}; аудит.
- `POST /api/admin/users/{id}/ban` (moderator+) — {active:bool}; аудит.

### 5. БЕЗПЕКА (privilege-escalation зона — найтвердіше)
- Зміна ролі — **лише admin**; НЕ можна змінити ВЛАСНУ роль (анти-self-lockout);
  роль ∈ дозволений набір (CHECK).
- **Не лишити систему без admin:** не можна знизити/забанити ОСТАННЬОГО активного admin.
- Бан: moderator керує user + collector (рішення оператора 2026-07-26), але НЕ чіпає
  admin/moderator; admin — будь-кого, крім себе й останнього admin. Забанений →
  login 403, наявний JWT доживає до exp (короткий TTL прийнятний; kill — окремо, не v1).
- Усі мутації — в `admin_audit` (actor, action, target, detail).

### 6. DoD
- [ ] 0170 + db (list_users/metrics/set_role/set_active з захистами + audit-запис).
- [ ] Гейти + 4 ендпойнти; login відхиляє is_active=false.
- [ ] Тести: гейт (user→403, moderator на role→403, admin→ok); анти-self-lockout;
      останній-admin захист; moderator не чіпає admin; аудит пишеться; login забаненого.
- [ ] MAUI (E2): «Адмін-панель» у профілі (лише moderator+): список юзерів + метрики;
      зміна ролі (лише admin) + бан.

### 7. Guardrails
- Ролі роздає лише admin; кожна зміна — в аудит (незмінний слід).
- Гість НЕ роль — не додавати 'guest' у CHECK (аноним = без токена).
- collector лишається (S10/S11 збір тримається на ній).

---
## Outcome

**E1 (сервер) — ЗРОБЛЕНО 2026-07-26.** 0170 (`app_user.is_active` + `admin_audit`);
гейти `require_moderator`/`require_admin`; 4 ендпойнти (users/metrics/role/ban);
login відхиляє забаненого (403). Захисти: не власна роль, last-admin guard (демоут І бан),
moderator↛admin/moderator, аудит кожної мутації. `AdminForbidden`(403) відділено від
`AdminError`(400) — межа прав ≠ порушення правила.

**Evidence E1:** CI ран 30194630059 — `200/200 passed` (test_api), обидва джоби зелені.
Ключові: «moderator банить admin → 403», «забанений user не входить → 403»,
«moderator банить collector → 200», «демоут останнього admin → AdminError»,
«set_role над собою → 400», «admin_audit пише слід». Деплой на прод: міграція 170
застосована, API живий; живий smoke — усі 4 ендпойнти без токена/зі сміттєвим → 401,
`/api/freshness` → 200 (публічне не зламалось).

**E2 (MAUI) — ЗРОБЛЕНО 2026-07-26.** AdminPage + AdminViewModel: список акаунтів
(роль людськими словами), метрики, pull-to-refresh; «Роль» (ActionSheet+підтвердження,
лише admin) і бан/розбан (підтвердження). Після дії — перечит із сервера. Відмови
сервера показуються ТЕКСТОМ як є. Вхід у профілі під `IsModerator`.
Збірка net10.0-android: **0 errors**. Прогін на емуляторі: під роллю collector кнопки
«Адмін-панель» немає — гейт ховає вхід (негативна перевірка).

**⚠ Лишилось (крок оператора, 🧭):** у системі 0 адмінів — першого призначає власник
SQL-ом (bootstrap; далі ролі роздаються з панелі). Повний UI-прогін панелі — після цього.

**Політика зама** (рішення оператора 2026-07-26): moderator керує user + collector,
не чіпає admin/moderator. Зафіксовано тестом.
