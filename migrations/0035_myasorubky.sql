-- 0035: нова категорія МʼЯСОРУБКИ (дрібна кухня).
--
-- Добрий матчер: бренд+модель (BOSCH MFWS440B, Tefal NE109838, Zelmer ZMM4080B) →
-- extract_mpn 70-92% (Foxtrot 33/42, Moyo 22/24, Epicentr 42/60), 25 ключів у 2+ крамницях.
--
-- 7 appliance-крамниць (Citrus пропущено — гаджетний профіль, meat-grinder-URL не знайдено).
-- Rozetka на bt-піддомені. Апостроф — ʼ (U+02BC), не SQL-лапка (інакше екранування ламає
-- регекс тесту catalog-meta). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Мʼясорубки', 'myasorubky')
ON CONFLICT (slug) DO NOTHING;
