# Задача S1 — `0001` схема (Postgres/Timescale) + DB-пул + персист RawItem

**Роль:** Виконавець (код) · **Автор:** Диригент, 2026-07-16 · **Статус:** `done` (верифіковано CI)
**Залежності:** S2 (`RawItem`). **Розблоковує:** `detect_pass` (S3), персист збору.

### 1. Ціль
Застосовна міграція `0001_init.sql` (уся схема §6), Python DB-пул (`DATABASE_URL` з env), міграційний раннер (`schema_migration`), і мінімальний персист `RawItem` → `store_product`+`price_snapshot`. Тест перевіряє DoD §6.6 проти **живого** Postgres 16 + TimescaleDB.

### 2. Контекст
- **`06-model-danih.md`** — канонічна схема (hypertable, continuous aggregate, компресія, `tsvector`, append-only тригер, BIGINT-копійки, форвардні міграції).
- §8.10.1 (central деплой, `DATABASE_URL` секрет), `workflow/07-conventions.md` (секрети через env, ніколи в репо).

### 3. Definition of Done (перевіряється тестом проти живої БД)
- [ ] `0001_init.sql` застосовується чисто; `schema_migration`=1.
- [ ] `timescaledb` встановлено; `price_snapshot` — **hypertable** (PK містить `seen_at`).
- [ ] append-only: `UPDATE`/`DELETE` по `price_snapshot` **реально падають** (тригер).
- [ ] `store_product.title_tsv` (GIN) присутній; `price_daily` — continuous aggregate + refresh-політика; компресія-політика активна.
- [ ] датовані config мають чинний рядок на `today`.
- [ ] **round-trip:** `RawItem` (з S2) персиститься → `store_product` (upsert `UNIQUE(source_id,external_ref)`) + `price_snapshot` insert; ціни цілі копійки.
- [ ] DB-пул із `statement_timeout`/`lock_timeout`; `DATABASE_URL` лише з env.

### 4. Поза скоупом
`detect_pass`/бейджі, read-API, Mini App, GH-деплой, `REVOKE`-роль (деплой-крок §8.10.1 — тригер уже тримає append-only в тесті).

### 5. Guardrails
- Гроші `BIGINT`-копійки; жоден float у сховище (A1).
- `DATABASE_URL` — **лише env/secret**, ніколи в репо/логах (git-безпека §8).
- Міграції форвардні, у транзакції; невдала → відкат.

### 6. ⚠ Середовище
Пісочниця **без Docker/WSL/локального Postgres**; TimescaleDB не має Windows-збірки. Тому тест **skip-aware**: без `DATABASE_URL` — пропуск (не провал). Верифікація — коли є Timescale: **Docker Desktop локально** (`timescale/timescaledb:latest-pg16`) або **Timescale Cloud** (`DATABASE_URL` в env, не в чат/репо).

---
## Outcome (Виконавець)

**✅ ВЕРИФІКОВАНО проти живого TimescaleDB (CI run 29495439389, job `migration`, 2026-07-16): 10/10 DoD-перевірок PASS з першого прогону, без правок `0001`.** Postgres-лог підтвердив append-only тригер (`ERROR: price_snapshot append-only (спроба UPDATE/DELETE заблокована)`). `create_hypertable`/cagg(tz-`time_bucket`+`last()`)/компресія/`pgconn.exec_`(cagg-не-в-txn) — усе спрацювало. **S1 закрито.**

---
_Первинний запис (до верифікації):_

**Статус: `code-complete / unverified-live`** (2026-07-16). Збудовано: `migrations/0001_init.sql` (уся §6-схема), `db/pool.py` (пул + `statement_timeout`/`lock_timeout`, `DATABASE_URL` з env), `db/migrate.py` (форвардний раннер, `schema_migration`), `db/store.py` (персист `RawItem`→`store_product`+`price_snapshot`), `tests/test_migration.py` (skip-aware DoD-тест), `requirements.txt` (+psycopg), `tests.yml` (job `migration` з Timescale-сервісом).

**Evidence (локально):** db-модулі імпортуються (psycopg 3.3.4 на Py3.14); `probe`/`pethouse` **18/18**; `test_migration` **чисто пропускається** без `DATABASE_URL`.

**⚠ НЕ верифіковано проти живого Timescale.** Пісочниця без Docker/WSL/Postgres; TimescaleDB не має Windows-збірки. **Верифікація — у CI:** `tests.yml → migration` піднімає `timescale/timescaledb:latest-pg16` (service) і ганяє `test_migration` (застосовує `0001`, перевіряє DoD §6.6). Запрацює на **першому пуші** на GitHub. Або локально: `$env:DATABASE_URL=...; python tests/test_migration.py`.

**Місця ризику на першому живому прогоні (де очікувати правок):**
1. **cagg не в транзакції** — оброблено: раннер виконує скрипт через `pgconn.exec_` (simple protocol, autocommit), не в явній txn.
2. Сигнатури Timescale: `create_hypertable(..., chunk_time_interval=>)` (класична), `add_compression_policy`, `add_continuous_aggregate_policy`, `time_bucket(..., 'Europe/Kyiv')` та `last()` у cagg — усі мали б бути на pg16-образі, але це перше, що перевіряю живцем.
3. `REVOKE`-роль append-only — поза `0001` (деплой §8.10.1); тест покладається на **тригер** (він перевіряється: UPDATE/DELETE мусять падати).

**DoD:** код повний; перевірки DoD **написані в тесті**, виконаються на живому Timescale (CI). Round-trip: касета S2 (9 варіантів) → `store_product`+`price_snapshot`, звірка Royal Canin 4кг = 170000/200000 копійок.

## Рев'ю (Диригент)
_(порожньо)_
