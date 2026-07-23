-- 0078: нова категорія ЗВОЛОЖУВАЧІ ПОВІТРЯ (Клімат).
--
-- ✓ СИЛЬНИЙ cross-store матчер (нарешті, як побутова техніка) — преміум-бренди з чистим
-- кодом домінують (Xiaomi, Philips HU..., Hyundai MINJI60, Deerma DEM-, Electrolux EHU-).
-- Заміряно 2026-07-23: extract_mpn Epicentr 19/60, Foxtrot 18/42, Allo 20/60 → 14 спільних
-- ключів у 2+ крамницях. Per-store історія повна.
--
-- 7 крамниць. Rozetka на bt-піддомені (humidifiers). Foxtrot broad uvlagniteli_vozduha,
-- Moyo під klimaticheskaya-tekh. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Зволожувачі повітря', 'zvolozhuvachi')
ON CONFLICT (slug) DO NOTHING;
