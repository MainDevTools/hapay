-- 0026: нова категорія ПРОЦЕСОРИ — четвертий ПК-компонент Фази B.
--
-- CPU несуть артикул/модель у назві (AMD Ryzen 7 7700X Box 100-100000..., Intel Core
-- i5-12400) → extract_mpn ~38-100% (нижче за SSD, бо частину пишуть модельною назвою без
-- box-SKU). Заміряно 2026-07-22 на 6 крамницях: 42 ключі у 2+ крамницях (Foxtrot 100%,
-- KTC 77%) — між відеокартами (30) і SSD (51). Сильний матчер.
--
-- Листинги в 10 крамницях (усі, крім Citrus — JS-app, і Vencon — не продає). Rozetka на
-- піддомені hard.rozetka.com.ua. Бекфілу нема — новий збір. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Процесори', 'procesory')
ON CONFLICT (slug) DO NOTHING;
