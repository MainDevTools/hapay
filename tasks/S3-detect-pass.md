# Задача S3 — `detect_pass`: обчислення бейджа (§5)

**Роль:** Виконавець (код) · **Автор:** Диригент, 2026-07-16 · **Статус:** `in-progress`
**Залежності:** S1 (схема+персист), S2 (RawItem). **Ядро продукту.**

### 1. Ціль
`detection/core.py` — **чиста** функція `compute_badge(історія, now, cfg, current, declared_old, announce?)` → стан бейджа §5.3. `detection/runner.py` — `detect_pass(conn)`: читає `price_snapshot`, рахує, **upsert `discount_event`** (§8.4). Ядро тестується синтетичними історіями офлайн; runner — проти живого Timescale (CI).

### 2. Контекст
- **`05-detektsiya.md`** — алгоритм: Стадія A (§5.1) + Стадія B (§5.2, 30-денний MIN із сирого), стани §5.3 (verified/verified_provisional/pumped/insufficient_history/declared), крайні §5.5, числа §5.7.
- §6.4 `discount_event` (upsert `UNIQUE(store_product_id, announce_date)`); §8.4 (announce відкритої події **не** перераховується); §5.1 `pct()` ROUND_HALF_UP.

### 3. Definition of Done
- [ ] `pct(d,b)` — Decimal ROUND_HALF_UP (4,5%→5%, не банкірське).
- [ ] Стадія A: `declared_pct` + sanity (`declared_ratio_max`, old<current → не показуємо).
- [ ] Стадія B: вікно [announce−30д, announce), лише `in_stock`+`>0`; `reference_kop=min`; `verified_pct`.
- [ ] Стани §5.3: `insufficient_history`/`declared` (мало точок) · `pumped` (verified<поріг) · `verified_provisional` (≥4 і <10 точок / вікно <30д) · `verified` (≥10 і повні 30д).
- [ ] OOS-точки виключені; guard проти `min([])`/поділу на 0.
- [ ] Синтетичні golden-історії → очікуваний бейдж (сходинка/pumped/insufficient/provisional/OOS), **час інжектований** (§8.8).
- [ ] `detect_pass(conn)`: upsert `discount_event`, **announce відкритої події заморожено** (§8.4); тест round-trip проти живого Timescale (CI).

### 4. Поза скоупом
UI/бейдж-рендер, `price_daily`-графік, закриття подій за discovery-відсутністю (окремо), «проти типової ціни» (M2+).

### 5. Guardrails
- `reference_kop`/бейдж — з **сирого `price_snapshot`**, ніколи `price_daily` (§5.2, юр).
- Гроші цілі копійки; жодного float у формулу порога (Decimal для %).
- Числа — з `detection_config`, не хардкод (§11.6).

---
## Outcome (Виконавець)

**Статус: `in-review`** (2026-07-16). Збудовано: `detection/core.py` (чиста логіка §5), `detection/runner.py` (`detect_pass`), `tests/test_detection.py` (7/7 синтетика), `tests/test_detect_pass.py` (CI-live), CI-кроки в `tests.yml`.

**Evidence:**
- **Ядро 7/7** (синтетичні історії, час інжектований): `pct` ROUND_HALF_UP (4,5%→5%), Стадія A + sanity, **verified** (30д→−20%), **verified_provisional** (8 точок), **pumped** (накачана→verified<0), **insufficient/declared**, **OOS виключено з бази** (не хибний pumped).
- Локальна регресія **25/25** (probe 9 + pethouse 9 + detection 7).
- `detect_pass` (verified + ідемпотентність) — верифікується в CI проти живого Timescale (job `migration`).

**DoD:** ✅ усі 5 станів §5.3; ✅ Стадія A sanity (`declared_ratio_max`); ✅ Стадія B вікно/reference із **сирого** `price_snapshot`; ✅ OOS/guard проти `min([])`; ✅ синтетичні golden; ✅ `detect_pass` upsert + **announce заморожено** (§8.4).

**Проєктні рішення / межі (чесно):**
- **Чисте ядро + DB-runner:** алгоритм §5 — без БД/годинника (тестований синтетикою §8.8); runner лише читає `price_snapshot` (київська доба через `AT TIME ZONE 'Europe/Kyiv'` у SQL) і робить upsert.
- **Подію заводимо лише для РЕАЛЬНОЇ знижки** (заявлена АБО інферована АБО вже відкрита) — інакше пласка ціна давала б хибний `pumped`.
- **Часткове покриття (уточнення далі):** `infer_announce_day` знаходить старт поточної кампанії з толерансом розривів < `campaign_gap_days`; заморожування announce відкритої події тримає «сходинку» (§5.2/§5.5). Повна багатокампанійна історична сегментація §5.5 + `campaign_gap` у **календарних** днях (не за індексом точок) — покрито базово, глибше тестування відкладено. Backfill-точки входять у вікно (вони в `price_snapshot`). Закриття подій за discovery-відсутністю (§8.4) — поза скоупом S3.

## Рев'ю (Диригент)
_(порожньо)_
