-- 0098: нова категорія ПРОЄКТОРИ (Електроніка).
--
-- ✓ СИЛЬНИЙ cross-store матчер — чистий концентрований SKU (Samsung SP-LPF/The Premiere,
-- XGIMI, Epson EB-, BenQ, Xiaomi, JMGO). Заміряно 2026-07-23: extract_mpn Foxtrot 31/42,
-- Epicentr 21/60, Allo 18/60 → 12 спільних ключів у 2+ крамницях. Per-store історія повна.
--
-- 4 крамниці (Foxtrot/Allo/Epicentr/Rozetka; Comfy/Eldorado/Moyo окремої категорії не
-- підтвердили). Rozetka на головному домені (projector). Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Проєктори', 'proektory')
ON CONFLICT (slug) DO NOTHING;
