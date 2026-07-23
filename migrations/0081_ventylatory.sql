-- 0081: нова категорія ВЕНТИЛЯТОРИ (побутові) (Клімат).
--
-- Добрий матчер: багато брендів із чистим кодом (Xiaomi, INTERLUX LFS-2828, Ardesto
-- FNM-X2G, Rowenta) — extract_mpn Epicentr 42/60, Foxtrot 29/42 → 11 спільних ключів у
-- 2+ крамницях (заміряно 2026-07-23). House-бренд UP! домішується, але не домінує.
-- Per-store історія повна.
--
-- Побутові (підлогові/настільні/колонні), НЕ витяжні (окрема категорія в крамницях).
-- 6 крамниць (Allo broad ventilyatory порожній через адаптер — можна дописати згодом).
-- Rozetka на bt-піддомені (fans). Moyo під klimaticheskaya-tekh. Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Вентилятори', 'ventylatory')
ON CONFLICT (slug) DO NOTHING;
