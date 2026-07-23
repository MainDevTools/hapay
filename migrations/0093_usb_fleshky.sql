-- 0093: нова категорія USB-ФЛЕШКИ (Електроніка / накопичувачі).
--
-- ✓ СИЛЬНИЙ cross-store матчер — чистий концентрований SKU (Kingston DataTraveler Exodia,
-- SanDisk, Samsung, Transcend, MediaRange). Заміряно 2026-07-23: extract_mpn Foxtrot 37/42,
-- Epicentr 43/60, Allo 44/60 → 21 спільний ключ у 2+ крамницях. Per-store історія повна.
-- (Одна з найсильніших категорій каталогу — поряд із SSD/GPU.)
--
-- 7 крамниць. Rozetka на головному домені (usb-flash-memory). Comfy flesh-and-usb, Moyo під
-- comp-and-periphery. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('USB-флешки', 'usb-fleshky')
ON CONFLICT (slug) DO NOTHING;
