-- 0069: нова категорія ОБПРИСКУВАЧІ (Садова техніка).
--
-- ⚠ Слабкий cross-store матчер (як садова — назви часто описові + бренд: 2E AquaSpray,
-- Marolex, Gardena) → extract_mpn дробить/None. Per-store історія повна. Верифіковано
-- 2026-07-23: Allo 58/60, Moyo 24/24.
--
-- 6 крамниць. Rozetka на головному домені (sprayers). Moyo слаг opryiskivateli (з yi),
-- Comfy hand-sprayers. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Обприскувачі', 'obpryskuvachi')
ON CONFLICT (slug) DO NOTHING;
