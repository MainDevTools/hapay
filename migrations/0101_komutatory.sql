-- 0101: нова категорія КОМУТАТОРИ (Електроніка / мережеве обладнання).
--
-- ✓ СИЛЬНИЙ cross-store матчер — чистий SKU (TP-Link TL-SF1005D/TL-SF1008D, Mercusys
-- MS106LP/MS108, Cudy GS108E, UGREEN). Заміряно 2026-07-23: extract_mpn Foxtrot 37/42,
-- Allo 43/60 → 14 спільних ключів у 2+ крамницях. Per-store історія повна.
--
-- Розширює мережеве поза наявними роутерами (routery). 5 крамниць (Epicentr слаг kommutatory
-- дав 404, Moyo не знайдено — можна дописати). Rozetka на головному домені (switches).
-- Comfy switch, Eldorado c1222573. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Комутатори', 'komutatory')
ON CONFLICT (slug) DO NOTHING;
