-- 0024: нова категорія ВІДЕОКАРТИ — сильний матчер Фази B.
--
-- На відміну від витяжок (слабкий матчинг), відеокарти дають ЧИСТИЙ артикул у назві
-- (ASUS DUAL-RTX5060TI-O8G, Gigabyte GV-N5070GAMING) → extract_mpn бере ~75-79%.
-- Заміряно 2026-07-22 на перших сторінках 4 крамниць: 30 ключів у 2+ крамницях
-- (KTC∩Foxtrot 13, KTC∩Telemart 13, Telemart∩Brain 9) — десятки крос-крамничних груп
-- одразу, на порядок більше за витяжки.
--
-- Листинги тегнуто прямо `videokarty` в 5 крамницях (Telemart/Brain/KTC/Foxtrot fetch/
-- render + Rozetka на піддомені hard.rozetka.com.ua). Бекфілу нема — новий збір.
-- Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Відеокарти', 'videokarty')
ON CONFLICT (slug) DO NOTHING;
