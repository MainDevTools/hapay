-- 0079: нова категорія ОЧИЩУВАЧІ ПОВІТРЯ (Клімат).
--
-- ✓ СИЛЬНИЙ cross-store матчер — преміум-бренди з чистим кодом (Philips AC3421/13, Dreo
-- DR-HAP006, Xiaomi, Toshiba CAF-X83XPL). Заміряно 2026-07-23: extract_mpn Epicentr 25/60,
-- Foxtrot 21/42, Allo 22/60 → 15 спільних ключів у 2+ крамницях. Per-store історія повна.
--
-- 7 крамниць. Rozetka на bt-піддомені (air_cleaners). Foxtrot слаг ionizatory (так у крамниці),
-- Moyo під klimaticheskaya-tekh. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Очищувачі повітря', 'ochyshchuvachi')
ON CONFLICT (slug) DO NOTHING;
