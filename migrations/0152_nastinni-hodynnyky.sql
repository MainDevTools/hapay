-- 0152: нова категорія НАСТІННІ ГОДИННИКИ (Годинники).
--
-- ⚠ ОДНЕ джерело: Rozetka bt c91456 (пошук-URL; цифровий слаг категорії).
-- Descriptive/дешевий сегмент — per-store Omnibus.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Настінні годинники', 'nastinni-hodynnyky')
ON CONFLICT (slug) DO NOTHING;
