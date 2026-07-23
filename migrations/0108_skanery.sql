-- 0108: нова категорія СКАНЕРИ (Офісна техніка).
--
-- ✓ СИЛЬНИЙ cross-store матчер — мало брендів, преміум домінує (Canon CanoScan Lide 400
-- (2996C010), Epson, Plustek). Заміряно 2026-07-23: extract_mpn Foxtrot 23/33, Allo 15/60,
-- Epicentr 14/60 → 14 спільних ключів у 2+ крамницях. Per-store історія повна.
--
-- Документні сканери (планшетні/протяжні), НЕ штрих-код/авто-сканери (окремі). 5 крамниць
-- (Eldorado/Moyo не знайдено). Rozetka на головному домені (scanners). Бекфілу нема.
-- Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Сканери', 'skanery')
ON CONFLICT (slug) DO NOTHING;
