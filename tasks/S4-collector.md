# Задача S4 — колектор (оркестрація fetch→extract→persist→detect_pass)

**Роль:** Виконавець (код) · **Автор:** Диригент, 2026-07-16 · **Статус:** `done` (CI 4/4 live)
**Залежності:** S1/S2/S3. **Робить конвеєр запускним** (Шар 1 §8.1).

> ✅ Верифіковано в CI (run 29497364326): collect на касеті → 9 снапшотів + scan_run + 8 declared-подій, 4/4. **Go-live:** провізія Timescale Cloud + секрет `DATABASE_URL` → `collect.yml` починає накопичувати реальну історію.

### 1. Ціль
`collect.py` — один вхід: для кожного джерела `scan_run` → fetch discovery-URL(и) → `adapter.extract` → `persist_items` → наприкінці `detect_pass`. Scheduled GH-workflow ганяє його наживо в постійну БД; CI-тест — детерміновано на касеті (інжектований `fetch`).

### 2. Контекст
- §8.1 (Шар 1), §8.2-central (GH Actions cron), §8.4 (`SourceAdapter`, detect_pass після scan_run), §10.1/§10.2 (каденс/ввічливість), §3.3 (Pethouse discovery — per-category `.../akcii/`).
- Наявне: `adapters/pethouse.py`, `db/store.py`, `detection/runner.py`, `db/migrate.py`.

### 3. Definition of Done
- [ ] `collect(conn, sources, fetch=...)` — DI-fetcher (тест на касеті, прод наживо).
- [ ] `scan_run` заводиться (surface='discovery'), оновлюється `items_seen`/`finished_at`.
- [ ] Дедуп `external_ref` між сторінками; персист через `persist_items`; наприкінці `detect_pass`.
- [ ] `main()` — з `DATABASE_URL` (env); **skip-aware** без нього (не червонити scheduled без секрета).
- [ ] CI-тест: collect на касеті → 9 снапшотів + `declared`-події (одиночний прогін = без історії).
- [ ] `collect.yml` — scheduled (кожні ~6 год) + `workflow_dispatch`, секрет `DATABASE_URL`.

### 4. Поза скоупом
baseline-поверхня (лістинги категорій), кілька адаптерів, headless, проксі, ретраї/бекоф — далі. Реальна таксономія (усе → `uncategorized` поки).

### 5. Guardrails
- Ввічливість §10.2 (пауза+джиттер між URL одного хоста); лише discovery-URL(и) з реєстру.
- Гроші цілі копійки (успадковано); лише-факти (§7.4).
- Секрет `DATABASE_URL` — лише в Actions secrets, ніколи в репо (git-безпека §8).

---
## Outcome (Виконавець)
_(в роботі)_
## Рев'ю (Диригент)
_(порожньо)_
