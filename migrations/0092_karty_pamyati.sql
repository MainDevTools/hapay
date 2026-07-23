-- 0092: нова категорія КАРТИ ПАМʼЯТІ (Електроніка / накопичувачі).
--
-- ✓ СИЛЬНИЙ cross-store матчер — чистий концентрований SKU (SanDisk, Kingston Canvas,
-- Samsung EVO, Goodram, MediaRange, Kioxia). Заміряно 2026-07-23: extract_mpn Foxtrot
-- 40/42, Epicentr 34/60 → 9 спільних ключів у 2+ (лише 2 крамниці в пробі). Per-store
-- історія повна.
--
-- 6 крамниць (Allo слаг karty-pamjati дав 404 — можна дописати згодом). Rozetka на головному
-- домені (memory-cards). Moyo під comp-and-periphery. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Карти памʼяті', 'karty-pamyati')
ON CONFLICT (slug) DO NOTHING;
