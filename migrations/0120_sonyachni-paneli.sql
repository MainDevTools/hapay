-- 0120: нова категорія СОНЯЧНІ ПАНЕЛІ (Енергія).
--
-- Матчер заміряно 2026-07-23: слабкий — 2 спільні ключі (Epicentr 20/60,
-- Allo 26/60; EcoFlow-панелі перетинаються, дрібні бренди XP/Kvant — ні).
-- 3 джерела: Epicentr + Allo (парсингом) + Rozetka c4629920 (пошук-URL).
-- Портативні й стаціонарні мішані — як ділять крамниці. Per-store Omnibus повний.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Сонячні панелі', 'sonyachni-paneli')
ON CONFLICT (slug) DO NOTHING;
