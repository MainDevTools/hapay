-- 0088: нова категорія МОЛОКОВІДСМОКТУВАЧІ (Дитячі товари).
--
-- ⚠ Слабкий матчер (як уся baby-вертикаль): преміум із чистим кодом (Philips Avent SCF,
-- Medela) є, але домінують дешеві бренди з descriptive-назвами (Canpol Babies, Applebear,
-- Swan Baby) → extract_mpn Epicentr 8/60, Allo 8/60, 0 спільних ключів у 2+ (заміряно
-- 2026-07-23). Per-store історія цін повна.
--
-- 3 крамниці (Rozetka/Allo/Epicentr; Foxtrot слаг не знайдено, Comfy — окремими товарами).
-- Rozetka на головному домені (breast_pumps). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Молоковідсмоктувачі', 'molokovidsmoktuvachi')
ON CONFLICT (slug) DO NOTHING;
