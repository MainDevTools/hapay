# Задача S6 — адаптери: PetChoice (тир A) + Horoshop-клас (тир B)

**Роль:** Виконавець (код) · **Автор:** Диригент, 2026-07-16 · **Статус:** `in-progress`
**Залежності:** S2 (контракт екстрактора), S4 (реєстр collect). **Ширше покриття крамниць.**

### 1. Ціль
- **PetChoice** — SSR-екстрактор (`product-price-old`, тир A §3.3) на касеті.
- **Horoshop-клас** — платформна родина (§3.6): MasterZoo, Petmarket. Тир B (сесійна кука `HOROSHOP_PHPSESSID`); екстракція JSON-LD-first / oldPrice. Колектор має підтримати cookie-fetch (тир B).

### 2. Контекст
- §3.3 (PetChoice `/discounts`, MasterZoo `/ua/aktsii/`), §3.5 (тири: B = сесійна кука, приймання ≠ обхід §7.4), §3.6 (Horoshop-родина = один клас, конфіг на крамницю), §4.1–4.4 (методи), §4.8 (дизамбігуація/`external_ref`).
- Наявне: `adapters/base.py`, `adapters/pethouse.py` (взірець), `collect.py` (реєстр SOURCES + fetch).

### 3. Definition of Done
- [ ] `PetChoiceAdapter.extract` → `RawItem` з коректними old/now копійками; golden-тест на обрізаній касеті.
- [ ] `HoroshopAdapter.extract` (config на крамницю: base_url/discount_url) — на касеті MasterZoo; JSON-LD або oldPrice.
- [ ] Колектор: **tier-B cookie-fetch** (GET→прийняти `Set-Cookie`→повторний GET) для Horoshop.
- [ ] Реєстрація в `collect.py` SOURCES (PetChoice + MasterZoo/Petmarket) з адаптером/тиром/URL.
- [ ] Тести зелені (pure + за потреби live на касетах у CI).

### 4. Поза скоупом
CAPTCHA-крамниці (Zootovary), headless, baseline-поверхня, реальна таксономія. Якщо Horoshop-розмітка виявиться JS-гідратованою без SSR-цін — позначити й відкласти (не воювати).

### 5. Guardrails
- Приймання сесійної куки — так; обхід CAPTCHA/техзахисту — ні (§7.4).
- Селектори семантичні (не повний клас-рядок); гроші цілі копійки; лише-факти.
- Касети обрізані, без байтів фото (git-безпека §8).

---
## Outcome (Виконавець)
_(в роботі)_
## Рев'ю (Диригент)
_(порожньо)_
