# Задача S6 — адаптери: PetChoice (тир A) + Horoshop-клас (тир B)

**Роль:** Виконавець (код) · **Автор:** Диригент, 2026-07-16 · **Статус:** `done` (PetChoice ✅ · Horoshop відкладено з обґрунтуванням)
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

**Статус: `in-review`** (2026-07-16).

**✅ PetChoice (тир A, miniShop2) — готово й у CI.** `adapters/petchoice.py` (картка `form.ms2_form`, мультиваріант `li.product-option`, поточна ціна `button[data-product-price]` чиста, стара — split грн+коп), касета `petchoice_akcii.html`, `test_petchoice` **5/5**. Зареєстровано в `collect.SOURCES`; `test_collect` оновлено під 2 джерела (**12 снапшотів / 11 declared** — verified live CI). На повній сторінці: 78 варіантів / 24 товари, 0 порушень now<old.

**⏸ Horoshop-клас — ВІДКЛАДЕНО; розвідку XHR (E) ЗАВЕРШЕНО з чітким вироком.** Тир-B кука `HOROSHOP_PHPSESSID` приймається (§3.5 — не обхід), але акції-лістинг гідратований client-side. **Розвідка E (браузер + мережевий аналіз, 2026-07-16):**
- **MasterZoo:** `window.StoreDataBig` тягне ціни **зовнішнім Vercel-сервісом** `product-import-lilac.vercel.app/product-import` (POST per артикул) + мерж знижок + фільтр складів. Bespoke, не в HTML.
- **Petmarket:** той самий Horoshop-JS; лістинг client-side, **0 цінових елементів у DOM** після рендеру; `/aktsii/`→промо-home.
- **Вирок:** чистого catalog-XHR для реверсу **немає** — потрібен **headless** (§4.7, `nodriver`, поза M1). Horoshop тир фактично **B→C**. MasterZoo-Vercel-хак — крихкий/не-генерик/чужий сервіс → **не будуємо**. Вписано в §3.3 і **§3.6** (теза «oldPrice за кукою» застаріла для всієї родини). **Позитив розвідки:** зекономлено від будування крихкого хака; Horoshop-важіль (8000+ §3.6) тепер має **чітку ціну входу — headless-під-проєкт M2+**, а не «легкий CSS».

**Підсумок:** покриття зросло з 1 до **2 крамниць** (Pethouse+PetChoice, обидві тир A SSR, мультиваріант). Horoshop (найбільший важіль §3.6) чекає на XHR/headless-під-проєкт.

**S6-G (розвідка нових SSR-крамниць 2026-07-16):** пробіг кандидатів (Foxtrot/Moyo/Citrus/E-Zoo/Zoobonus/Kormax) наживо — **нових чистих тир-A SSR-лістингів немає**: Foxtrot — Next.js/SPA (0 цін у DOM), Citrus `/shares/` — кампанійний індекс, решта 404/лендинг/JS. **Емпіричний висновок: чистий SSR-discovery = фактично Pethouse+PetChoice; ринок пішов у client-side** (як Horoshop). Тому — **розширив покриття в межах Pethouse**: підтверджено пробою **6 категорій** (suhoi-korm/konservi/shampuni × кот/пес, ~303 варіанти проти 84) → усі в `collect.SOURCES` discount_urls. `collect()` дістав `delay`-параметр (ввічливість; тест=0).

## Рев'ю (Диригент)
_(порожньо)_
