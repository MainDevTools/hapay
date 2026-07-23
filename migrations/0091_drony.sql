-- 0091: нова категорія КВАДРОКОПТЕРИ ТА ДРОНИ (Фото-відео).
--
-- ⚠ СЛАБКИЙ матчер: категорія розмита дешевими ІГРАШКОВИМИ дронами (KEHANG E88, Nomi,
-- Overmax) з descriptive-назвами; преміум (DJI, Autel) — меншість → extract_mpn Allo 18/60,
-- 0 спільних ключів у 2+ (заміряно 2026-07-23). Foxtrot-категорія тонка (5 товарів, FPV/
-- EMAX). Per-store історія повна.
--
-- 6 крамниць. Rozetka на головному домені (quadrocopters). Comfy drony, Eldorado node
-- c1225224. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Квадрокоптери та дрони', 'drony')
ON CONFLICT (slug) DO NOTHING;
