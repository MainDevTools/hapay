-- 0094: нова категорія ЗОВНІШНІ ЖОРСТКІ ДИСКИ (Електроніка / накопичувачі) — завершує
-- кластер накопичувачів.
--
-- ✓ СИЛЬНИЙ cross-store матчер — чистий концентрований SKU (WD Elements/My Passport,
-- Seagate Expansion, Transcend StoreJet, Toshiba Canvio, LaCie). Заміряно 2026-07-23:
-- extract_mpn Foxtrot 41/42, Allo 60/60, Epicentr 28/60 → 24 спільні ключі у 2+ крамницях.
-- Per-store історія повна.
--
-- 6 крамниць. Rozetka на hard-піддомені (hdd c80084 — переважно зовнішні для споживача).
-- Epicentr zhestkie-diski (трохи внутрішніх домішується). Comfy portable-hard-disk. Бекфілу
-- нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Зовнішні жорсткі диски', 'zovnishni-hdd')
ON CONFLICT (slug) DO NOTHING;
