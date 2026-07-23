-- 0095: нова категорія РАДІОНЯНІ ТА ВІДЕОНЯНІ (Дитячі товари).
--
-- ⚠ Слабкий матчер (як уся baby-вертикаль): преміум (Motorola, Philips Avent, Lionelo,
-- VTech) є, але домінують дешеві no-name (Andowl, Baby Monitor SM-650, Yikoo) з descriptive-
-- назвами. Per-store історія повна.
--
-- 3 крамниці (Rozetka/Allo/Epicentr; Foxtrot слаг не знайдено). Rozetka на головному домені
-- (babymonitors). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Радіоняні та відеоняні', 'radionyani')
ON CONFLICT (slug) DO NOTHING;
