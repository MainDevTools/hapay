-- 0082: нова категорія МЕТЕОСТАНЦІЇ (Клімат) — завершує дрібніший клімат.
--
-- ⚠ СЛАБКИЙ/каламутний матчер: категорія змішує дешеві термометри/гігрометри (Склоприлад,
-- без коду) з брендовими станціями (EMOS E6016, Technoline WS6760). Крамниці наповнюють
-- по-різному: Epicentr — переважно термометри (MPN 3/60), Allo — станції (MPN 38/60),
-- Foxtrot проміжно (9/42) → 0 спільних ключів у 2+ (заміряно 2026-07-23). Per-store історія
-- повна.
--
-- 7 крамниць. Rozetka на bt-піддомені (miniweather_stations). Foxtrot слаг meteostanchii,
-- Moyo meteostancyi під klimaticheskaya-tekh. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Метеостанції', 'meteostantsii')
ON CONFLICT (slug) DO NOTHING;
