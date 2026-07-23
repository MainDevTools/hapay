-- 0076: нова категорія АВТОХОЛОДИЛЬНИКИ (Авто) — 12/24V холодильники для авто/подорожей.
--
-- ⚠ Слабкий cross-store матчер (назва часто бренд+об'єм: BREVIA 40л, Ranger Cool 19L,
-- GIOSTYLE Bravo25) → «40л» не код, extract_mpn дробить. Per-store історія повна.
-- Верифіковано 2026-07-23: Foxtrot 42/42, Epicentr 59/60, Allo 59/60.
--
-- Окремо від побутових холодильників (holodylnyky). 6 крамниць. Rozetka авто на піддомені.
-- Allo слаг portativnye-holodil-niki, Eldorado c1061580 (переносні). Бекфілу нема.
-- Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Автохолодильники', 'avtoholodylnyky')
ON CONFLICT (slug) DO NOTHING;
