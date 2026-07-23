-- 0066: нова категорія САДОВІ ПИЛОСОСИ ТА ПОВІТРОДУВКИ (Садова техніка).
--
-- ⚠ Слабкий cross-store матчер (як садова/DIY — багатотокенні коди: Bosch UniversalGarden
-- Tidy, AL-KO LBV 4090) → extract_mpn дробить. Per-store історія повна. Верифіковано
-- 2026-07-23: Allo 60/60, Moyo 24/24.
--
-- Об'єднана: повітродувки + садові пилососи (часто одна крамнична категорія, 2-в-1 моделі).
-- 6 крамниць. Rozetka на головному домені (blowers). Moyo під sadovaya_technika. Бекфілу
-- нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Садові пилососи та повітродувки', 'povitroduvky')
ON CONFLICT (slug) DO NOTHING;
