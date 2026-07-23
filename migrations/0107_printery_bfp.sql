-- 0107: нова категорія ПРИНТЕРИ ТА БФП — старт розділу «Офісна техніка».
--
-- ✓ СИЛЬНИЙ cross-store матчер — чистий SKU, преміум ДОМІНУЄ без дешевого хвоста (HP,
-- Canon PIXMA/i-SENSYS LBP623Cdw, Epson, Brother, Xerox Phaser 3020BI, Pantum P2500W,
-- Samsung). Заміряно 2026-07-23: extract_mpn Foxtrot 27/33, Allo 31/60, Epicentr 29/60 →
-- 13 спільних ключів у 2+ крамницях. Per-store історія повна.
--
-- Об'єднана принтери+БФП (крамниці переважно тримають однією: Rozetka printers-mfu, Allo
-- printery, Epicentr mnogofunktsionalnye-i-printery). 7 крамниць. Rozetka на головному
-- домені. Foxtrot/Moyo дроблять — беремо обидва листинги (printery+mfu / printer+mfu).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Принтери та БФП', 'printery-bfp')
ON CONFLICT (slug) DO NOTHING;
