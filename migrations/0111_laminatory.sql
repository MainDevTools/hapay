-- 0111: нова категорія ЛАМІНАТОРИ (Офісна техніка).
--
-- ⚠ Слабкий матчер: нішеві бренди (lamiMARK Senator 231, 2E L-403, 1A, LiDi) →
-- extract_mpn Allo 3/60. Per-store історія повна.
--
-- 3 крамниці (Rozetka/Allo/Epicentr; Foxtrot окремої категорії не має). Rozetka на головному
-- домені (laminator). Бекфілу нема. Forward-only, ідемпотентно.
--
-- (Презентери НЕ додаємо — немає окремої категорії в крамницях, лише 1 крамниця мішає їх
--  із лазерними указками.)

INSERT INTO category (name, slug) VALUES
  ('Ламінатори', 'laminatory')
ON CONFLICT (slug) DO NOTHING;
