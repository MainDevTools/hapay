-- 0025: нова категорія SSD-НАКОПИЧУВАЧІ — найсильніший матчер Фази B досі.
--
-- SSD несуть майже ідеальний артикул у назві (Kingston SNV3S/1000G, Samsung MZ-V9P2T0BW)
-- → extract_mpn ~88-100%. Заміряно 2026-07-22 на перших сторінках 6 крамниць: 51 ключ
-- у 2+ крамницях (Foxtrot/Allo 100% MPN, Telemart 94%, Epicentr 97%) — більше за
-- відеокарти (30). Найгустіша overlap-жила ПК-комплектуючих.
--
-- Листинги в 10 крамницях (усі, крім Citrus — JS-app, і Vencon — не продає). Rozetka на
-- піддомені hard.rozetka.com.ua. Бекфілу нема — новий збір. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('SSD-накопичувачі', 'ssd')
ON CONFLICT (slug) DO NOTHING;
