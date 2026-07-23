-- 0087: нова категорія ДИТЯЧІ АВТОКРІСЛА (Дитячі товари).
--
-- ⚠ Слабкий матчер (як коляски): бренд+модель словами, домінують дешеві (Auto Assistance,
-- Kidilo) → extract_mpn Epicentr 14/60, Allo 16/60, лише 2 спільні ключі у 2+ (заміряно
-- 2026-07-23). Per-store історія повна.
--
-- 4 крамниці (Rozetka/Allo/Epicentr/Foxtrot; Comfy автокрісла — під car-goods, неоднозначно,
-- пропущено). Rozetka на головному домені. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Дитячі автокрісла', 'avtokrisla')
ON CONFLICT (slug) DO NOTHING;
