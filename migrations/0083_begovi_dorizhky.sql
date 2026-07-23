-- 0083: нова категорія БІГОВІ ДОРІЖКИ — старт розділу «Спорт» (спорт/фітнес).
--
-- ⚠ Weak-medium матчер: бренди різняться по крамницях (MaxxPro TM20B, Everfit TFK, UREVO
-- SpaceWalk, KingSmith WalkingPad), коди напівчисті → extract_mpn Epicentr 21/60, Foxtrot
-- 11/42, Allo 8/60 → 4 спільні ключі у 2+ (заміряно 2026-07-23). Per-store історія повна.
--
-- 6 крамниць (Eldorado тренажерів не тримає — пропущено). Rozetka на головному домені
-- (treadmills). Foxtrot слаг trenazheriy_..._begovaya-dorozhka, Comfy facet sports-and-
-- recreation, Moyo під sport_otdih_turizm. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Бігові доріжки', 'begovi-dorizhky')
ON CONFLICT (slug) DO NOTHING;
