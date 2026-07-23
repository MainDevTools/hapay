-- 0096: нова категорія ДИТЯЧІ ВАГИ (Дитячі товари).
--
-- ⚠ ТОНКА + слабкий матчер: додано на явну вимогу оператора. Лише 2 крамниці — Rozetka
-- (окрема категорія detskie-vesy) + Epicentr (фасет підлогових ваг для немовлят; Allo
-- окремої не має, Foxtrot не знайдено). Бренди мішані (Beurer/Esperanza/Magio/Camry).
-- Per-store історія повна.
--
-- Rozetka на головному домені. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Дитячі ваги', 'dytyachi-vagy')
ON CONFLICT (slug) DO NOTHING;
