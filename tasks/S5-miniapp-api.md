# Задача S5 — read-API (FastAPI) + Telegram Mini App (§8.10.1/§9.7)

**Роль:** Виконавець (код) · **Автор:** Диригент, 2026-07-16 · **Статус:** `in-progress`
**Залежності:** S1 (схема), S3/S4 (discount_event). **Шар 3 (презентація).**

### 1. Ціль
Тонкий **read-only API** (FastAPI): category-first перелік знижок із фільтром/сортом/пагінацією (§9.1), історія товару для графіка (§9.2), категорії. **Mini App** (статичний HTML у Telegram): вітрина з бейджами + графік. Авторизація — Telegram `initData` (HMAC), клієнт **не** має прямого доступу до БД (§8.10.1).

### 2. Контекст
- §8.10.1 (read-API, initData-auth, клієнт без токена БД), §9.1 (перелік/фільтри), §9.2 (картка/графік inline-SVG), §9.7 (Mini App мобільний, тема Telegram, hotlink-фото), §5.3 (бейджі), §7.4 (фото — вказівник).

### 3. Definition of Done
- [ ] `verify_init_data(initData, bot_token)` — HMAC за спекою Telegram; свіжість `auth_date`. Юніт-тест (валід/підробка/протухле).
- [ ] `GET /api/discounts?category&badge&sort&page` — join `discount_event`+`store_product`; поля картки §9.1 (title, url, image_url, current/old/reference_kop, *_pct, badge_state).
- [ ] `GET /api/product/{id}/history` — точки для графіка (з `price_snapshot`/`price_daily`).
- [ ] `GET /api/categories`.
- [ ] Watchlist (POST/GET) — **гейт `initData`**, `tg_user_id` як ключ.
- [ ] Mini App `web/index.html` — category-first список, бейдж-чіпи/фільтр, hotlink-фото, тап→історія (inline-SVG); Telegram WebApp SDK + тема.
- [ ] Тести: initData (pure) + API проти живого Timescale (TestClient, дані через collect на касеті) у CI.

### 4. Поза скоупом
Хостинг/деплой API (окремий ops-крок, як go-live), push-бот, реальна таксономія-навігація, пагінація-нескінченний-скрол, кеш.

### 5. Guardrails
- Клієнт **без** прямого доступу до БД — лише через API (§8.10.1, безпека).
- `BOT_TOKEN`/`DATABASE_URL` — лише env/secret, ніколи в репо (git-безпека §8).
- Фото — тільки hotlink `image_url` (не байти, §7.4). Гроші — копійки, формат у грн лише на показ.

---
## Outcome (Виконавець)
_(в роботі)_
## Рев'ю (Диригент)
_(порожньо)_
