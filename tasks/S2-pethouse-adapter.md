# Задача S2 — адаптер Pethouse (екстрактор) на касеті

**Роль:** Виконавець (код) · **Автор:** Диригент, 2026-07-16 · **Статус:** `in-progress`
**Залежності:** S0.1 (probe довів ліквідність Pethouse). **НЕ** залежить від `0001`/БД — це чистий екстрактор.

### 1. Ціль
`PethouseAdapter.extract(html) -> list[RawItem]` для акції-лістингу Pethouse, тестований **детерміновано на записаній касеті** (обрізана реальна розмітка). Персист у `price_snapshot` — поза скоупом (потребує `0001`, S1).

### 2. Контекст
- §3.3 **Оновлення probe 2026-07-16** — Pethouse РЕДИЗАЙН: поточна `price-field`, стара `line-through`, знижка `-NN%` `bg-red`, юніт `грн/кг`, тир A SSR, JSON-LD нема.
- §8.4 (контракт `SourceAdapter`), §4.8 (дизамбігуація 5 цін, `external_ref` канонізація, «від X грн» → `needs_variant_resolution`), §4.1 (кодування).
- `workflow/02-invariants.md`: A1 гроші `BIGINT`-копійки; §8/git-безпека — касета обрізана, без байтів фото.

### 3. Definition of Done
- [ ] `RawItem` (dataclass): `external_ref, url, title, price_now_kop, price_old_kop, in_stock, unit_text?, variant_note?`.
- [ ] `parse_price_to_kop("2 000,00")==200000` — UA-формат (пробіл/nbsp тисячі, кома-децималь, ₴/грн, `від`).
- [ ] `PethouseAdapter.extract(cassette)` дає **≥2 картки** з коректними old/now копійками, дедуп `external_ref` (§4.8).
- [ ] **Golden-тест на касеті** `tests/cassettes/pethouse_akcii.html` (обрізана реальна) — точні очікувані значення.
- [ ] `price_now_kop < price_old_kop` для знижених; знижка% узгоджена з `-NN%`-бейджем (sanity).
- [ ] Тести зелені (`python tests/test_pethouse.py`).

### 4. Поза скоупом
БД/`0001`/персист, `detect_pass`, інші крамниці, headless, живий HTTP у тесті (лише касета).

### 5. Guardrails
- Гроші — цілі копійки, ніколи float (A1). Парс-помилка ціни → пропуск картки + лічильник, не 0/None-ціна в історію.
- Касета — обрізана до кількох карток, **без байтів фото/скриптів** (git-безпека §8; `image_url` як вказівник — можна).
- Стійкість до дрібних змін класів (не хардкодити повний Tailwind-рядок).

---
## Outcome (Виконавець)

**Статус: `in-review`** (2026-07-16). Збудовано: `adapters/base.py` (`RawItem`, `parse_price_to_kop`, `canon_ref`, `slugify`), `adapters/pethouse.py` (екстрактор на **selectolax**), `tests/cassettes/pethouse_akcii.html` (обрізана реальна, 2 товари), `tests/test_pethouse.py`, `requirements.txt` (selectolax), `.github/workflows/tests.yml` (CI-гейт #28).

**Evidence:**
- На **повній** сторінці (dev, не комітиться): **84 варіанти / 24 товари, 0 порушень now<old, 0 дублів `external_ref`**, копійки точні (`2 000,00`→200000).
- На **касеті**: 9 варіантів / 2 товари. Тести **18/18** (`test_pethouse` 9/9 + регресія `test_probe` 9/9).

**DoD:** ✅ `RawItem`; ✅ `parse_price_to_kop("2 000,00")==200000` (+nbsp/кома/₴/«від»); ✅ `extract` ≥2 картки з коректними old/now копійками, дедуп `#v=`; ✅ golden-тест на касеті (точні значення Royal Canin 4кг=170000/200000/−15%, 10кг=360000/480000/−25%); ✅ sanity now<old; ✅ зелено.

**🔴 Реальність-фідбек (→ §3.3, §4.8):**
1. **Картки Pethouse МУЛЬТИВАРІАНТНІ** — один товар (`div.group.relative.grid` + `a[href*="/ua/shop/"]` + `img alt`=назва) містить **кілька фасувань** (`div.py-4`), кожне зі своєю old/now/`-NN%`/грн-кг. Тому `line-through`=84 — це **варіант-рядки**, товарів ~24. → **один `RawItem` на варіант**, `external_ref = url#v=<варіант>` (підтверджує §4.8/GAP15 на живому прикладі).
2. **Не всі варіанти зі знижкою** — трапляється `old=None` (напр. Purina 3кг): екстрактор віддає без старої, не 0/помилку.
3. Фото — `img src` (вказівник, `pethouse.ua/assets/.../*.jpg`), у RawItem як `image_url`; байти не тримаємо (§7.4).

**Рішення/відхилення:**
- **selectolax** (стек §8.3) — працює на Python 3.14; тест адаптера його потребує → `requirements.txt` + `tests.yml`. probe лишається stdlib.
- Селектори **семантичні** (`price-field`/`line-through`/`bg-main-bg`/`bg-red`), не повний Tailwind-рядок → стійкі до дрібних змін утиліт.
- Каса — **обрізана** (2 картки, без svg/script; `img src` як вказівник) відповідно до git-безпеки §8.
- Персист у `price_snapshot` — поза скоупом (потребує `0001`, S1). `RawItem` уже під схему §6 (BIGINT-копійки, `external_ref`, `image_url`/`image_source`).

## Рев'ю (Диригент)
_(порожньо)_
