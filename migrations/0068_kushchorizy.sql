-- 0068: нова категорія КУЩОРІЗИ ТА САДОВІ НОЖИЦІ (Садова техніка).
--
-- ⚠ Слабкий cross-store матчер (як садова — багатотокенні коди: Bosch EasyHedgeCut,
-- Einhell GE-CG 18) → extract_mpn дробить. Per-store історія повна. Верифіковано
-- 2026-07-23: Foxtrot 42/42, Allo 55/60.
--
-- ⚠ Comfy слаг brush-cutters (кущорізи, З ДЕФІСОМ) ≠ brushcutters (мотокоси 0063, БЕЗ) —
-- легко сплутати, тримати окремо. 5 крамниць (Moyo/Eldorado не знайдено). Rozetka на
-- головному домені. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Кущорізи та садові ножиці', 'kushchorizy')
ON CONFLICT (slug) DO NOTHING;
