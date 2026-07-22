-- 0034: нова категорія ПРАСКИ (дрібна кухня/дім).
--
-- Добрий матчер: бренд+модель (Philips DST7030/20, Tefal FV2C41E0) → extract_mpn 90%+
-- (Foxtrot 40/42, Moyo 22/24, заміряно 2026-07-22). Категорія крамниць включає й
-- ВІДПАРЮВАЧІ (garment steamers) — свідомо, ад'яцентно (те саме прасування/відпарювання).
--
-- 8 appliance-крамниць. Rozetka на bt-піддомені. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Праски', 'prasky')
ON CONFLICT (slug) DO NOTHING;
