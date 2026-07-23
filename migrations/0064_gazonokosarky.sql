-- 0064: нова категорія ГАЗОНОКОСАРКИ (Садова техніка).
--
-- ⚠ Слабкий cross-store матчер (як DIY/садова — багатотокенні tool-коди: Bosch EasyRotak
-- 32, GRUNHELM EM-61) → extract_mpn дробить. Per-store історія цін повна. Верифіковано
-- 2026-07-23: Foxtrot 42/42, Epicentr 60/60, Allo 52/60.
--
-- 6 крамниць (Eldorado садової категорії не знайдено — пропущено). Rozetka на головному
-- домені (grass_cutters). Moyo під sadovaya_technika. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Газонокосарки', 'gazonokosarky')
ON CONFLICT (slug) DO NOTHING;
