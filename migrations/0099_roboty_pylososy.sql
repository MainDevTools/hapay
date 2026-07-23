-- 0099: нова категорія РОБОТИ-ПИЛОСОСИ (Побутова техніка).
--
-- ✓ Сильний cross-store матчер — концентровані преміум-бренди з чистим кодом (iRobot Roomba,
-- Roborock, Xiaomi Robot Vacuum, Dreame L40, Ecovacs Deebot, Mova). Заміряно 2026-07-23:
-- extract_mpn Epicentr 19/60, Foxtrot 11/42, Allo 10/60 → 8 спільних ключів у 2+ крамницях.
-- Per-store історія повна.
--
-- Окремо від звичайних пилососів (pylososy). 6 крамниць (Eldorado — лише фасет bagless,
-- пропущено). Rozetka на головному домені (clean_robots). Comfy vacuum-cleaning-robots, Moyo
-- під bt/mbt. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Роботи-пилососи', 'roboty-pylososy')
ON CONFLICT (slug) DO NOTHING;
