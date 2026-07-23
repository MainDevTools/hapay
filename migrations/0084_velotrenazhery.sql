-- 0084: нова категорія ВЕЛОТРЕНАЖЕРИ (Спорт).
--
-- ⚠ Weak-medium матчер (як бігові): бренди різняться (MaxxPro MB5, TOORX BRX, MERACH
-- MR-S07) → extract_mpn Foxtrot 27/42, Allo 11/60, Epicentr 7/60 → 4 спільні ключі у 2+
-- (заміряно 2026-07-23). Per-store історія повна.
--
-- 5 крамниць (Eldorado/Comfy окремої категорії не тримають — пропущено). Rozetka на
-- головному домені (exrecise_bikes). Moyo під sport_otdih_turizm. Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Велотренажери', 'velotrenazhery')
ON CONFLICT (slug) DO NOTHING;
