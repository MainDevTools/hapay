-- 0118: нова категорія МІКРОФОНИ (Фото-відео) — розгортання Fotosale ушир.
--
-- Стрімерсько-подкастний сегмент (Sony ECM, RODE): MPN 7/20, преміум помірний.
-- Джерело: Fotosale catalog_rub3020 (20 карток). Core-крамниці мають мікрофони
-- в аудіо-розділах — крос-довантаження можливе окремим кроком.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Мікрофони', 'mikrofony')
ON CONFLICT (slug) DO NOTHING;
