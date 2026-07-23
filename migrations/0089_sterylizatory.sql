-- 0089: нова категорія СТЕРИЛІЗАТОРИ ТА ПІДІГРІВАЧІ ПЛЯШЕЧОК (Дитячі товари).
--
-- ⚠ Слабкий матчер (як уся baby-вертикаль): Avent/Chicco чисті, але дешеві бренди (RZTK,
-- LELIK, Hausland, Canpol) з descriptive-назвами домінують. Per-store історія повна.
-- Верифіковано 2026-07-23: Allo 51/60, Epicentr 52/60 — профіль стерилізаторів/підігрівачів.
--
-- Об'єднана: стерилізатори + підігрівачі (крамниці тримають однією категорією — Rozetka
-- sterilizatori-i-podogrevateli, Epicentr podogrevateli-i-sterilizatory). 5 крамниць.
-- Rozetka на головному домені. Foxtrot — підігрівачі, Comfy — baby-bottle-warmers. Бекфілу
-- нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Стерилізатори та підігрівачі', 'sterylizatory')
ON CONFLICT (slug) DO NOTHING;
