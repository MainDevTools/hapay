-- 0115: нова категорія ПУЛЬСОКСИМЕТРИ (Медтехніка).
--
-- ⚠ Слабкий: 3 крамниці (Epicentr, Rozetka apteka-піддомен c4672048, Allo pul-soksimetry).
-- Домінують no-name китайські (Contec OX-832, Jziki PLS303, UKC 1906, BTR) — фрагментовано,
-- майже без збігів; extract_mpn Allo 4/60, Epicentr 8/60 → 0 спільних ключів. Allo-сторінка
-- pul-soksimetry ДОДАТКОВО мішає кардіодатчики Garmin HRM (пульсометри ≠ пульсоксиметри) —
-- store-side квірк таксономії. Per-store Omnibus-детекція повна.
--
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Пульсоксиметри', 'pulsoksimetry')
ON CONFLICT (slug) DO NOTHING;
