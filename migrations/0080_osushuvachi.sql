-- 0080: нова категорія ОСУШУВАЧІ ПОВІТРЯ (Клімат) — завершує кластер «повітря».
--
-- ✓ Сильний матчер (як зволожувачі/очищувачі) — чисті коди між крамницями (Gorenje D 20 M,
-- Cooper&Hunter CH-D008WDP7-20LD, Xiaomi Smart Dehumidifier, Deerma CS50MW, Neoclima SBN-012).
-- Per-store історія повна.
--
-- 6 крамниць (Moyo окремої категорії не знайдено). Rozetka на bt-піддомені. Foxtrot broad
-- osushiteli_vozduha, Comfy dehumidifiers, Eldorado air_dryers. Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Осушувачі повітря', 'osushuvachi')
ON CONFLICT (slug) DO NOTHING;
