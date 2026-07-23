-- 0086: нова категорія ДИТЯЧІ КОЛЯСКИ — старт розділу «Дитячі товари».
--
-- ⚠ СЛАБКИЙ матчер (як ручний інструмент): назви descriptive (Ninos Ventura 3в1,
-- Baobaohao A5, Carrello Alfa — бренд+модель словами), домінують дешеві бренди без коду →
-- extract_mpn Epicentr 10/60, Allo 8/60, 0 спільних ключів у 2+ (заміряно 2026-07-23).
-- Per-store історія цін повна (дорогі товари, накрутки часті — цінно навіть без cross-store).
--
-- 5 крамниць (Rozetka/Allo/Epicentr — baby-профіль; Foxtrot/Comfy мають kids-розділ).
-- Rozetka на головному домені. Moyo/Eldorado — можна дописати згодом. Бекфілу нема.
-- Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Дитячі коляски', 'kolyasky')
ON CONFLICT (slug) DO NOTHING;
