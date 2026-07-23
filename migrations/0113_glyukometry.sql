-- 0113: нова категорія ГЛЮКОМЕТРИ (Медтехніка).
--
-- ⚠ Слабкий + тонкий: 2 крамниці (Rozetka apteka-піддомен + Allo). Descriptive-назви
-- («Longevita Family Система...»), дешеві бренди (Longevita, XPRO, Infopia) домінують над
-- преміум (Accu-Chek, OneTouch, Contour) → extract_mpn Allo 0/60. Per-store історія повна.
--
-- Rozetka на apteka-піддомені (глюкометри — товар аптеки). Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Глюкометри', 'glyukometry')
ON CONFLICT (slug) DO NOTHING;
