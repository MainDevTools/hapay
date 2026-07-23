-- 0097: нова категорія СТІЛЬЧИКИ ДЛЯ ГОДУВАННЯ (Дитячі товари).
--
-- ⚠ Слабкий матчер (як уся baby-вертикаль): назви descriptive (стілець 6в1/3в1, бренди
-- El Camino/Bambinelli/Kidilo/Moolino), домінують дешеві → низький cross-store. Per-store
-- історія повна.
--
-- 3 крамниці (Rozetka/Allo/Epicentr). Rozetka на головному домені (stulchiki-dlya-kormleniya).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Стільчики для годування', 'stilchyky')
ON CONFLICT (slug) DO NOTHING;
