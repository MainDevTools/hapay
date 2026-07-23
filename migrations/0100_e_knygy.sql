-- 0100: нова категорія ЕЛЕКТРОННІ КНИГИ (Електроніка).
--
-- ✓ СИЛЬНИЙ cross-store матчер — концентрований чистий SKU (PocketBook 629/634/619 Verse,
-- Amazon Kindle, AIRBOOK). Заміряно 2026-07-23: extract_mpn Foxtrot 11/19, Allo 20/60,
-- Epicentr 9/25 → 11 спільних ключів у 2+ крамницях. Per-store історія повна.
--
-- 7 крамниць. Rozetka на головному домені (e-books). Comfy electronic-book, Moyo під
-- tablet_el_knigi. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Електронні книги', 'e-knygy')
ON CONFLICT (slug) DO NOTHING;
