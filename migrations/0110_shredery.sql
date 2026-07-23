-- 0110: нова категорія ШРЕДЕРИ (знищувачі документів) (Офісна техніка).
--
-- ⚠ ТОНКА + слабкий матчер: лише 2 крамниці (Rozetka standalone + Allo; Foxtrot/Epicentr
-- окремої категорії не мають). Назви descriptive, домінують нішеві бренди (Bonsaii, Agent,
-- HP OneShred, Fellowes) → extract_mpn Allo 0/60. Per-store історія повна.
--
-- Rozetka на головному домені (shredders). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Шредери', 'shredery')
ON CONFLICT (slug) DO NOTHING;
