-- 0146: нова категорія ОВЕРЛОКИ (Шиття).
--
-- ⚠ ОДНЕ джерело: Rozetka bt/overloki c4670141 (чиста, пошук-URL); в Epicentr
-- оверлоки мішані у shveynaya-tekhnika (5/60 — залишаються там), Allo категорії
-- не знайдено. Janome/Merrylock коди. Per-store Omnibus.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Оверлоки', 'overloky')
ON CONFLICT (slug) DO NOTHING;
