-- 0027: нова категорія ОПЕРАТИВНА ПАМ'ЯТЬ (RAM) — п'ятий ПК-компонент Фази B.
--
-- RAM несе майже ідеальний артикул (Kingston FURY KF556C40BBK2-32, Kingston ValueRam
-- KVR32N22S8/8) → extract_mpn 75-100%. Заміряно 2026-07-22 на 6 крамницях: 37 ключів
-- у 2+ крамницях (Telemart/KTC/Foxtrot/Moyo 100% MPN). Сильний матчер, поряд із CPU.
--
-- Листинги в 10 крамницях (усі, крім Citrus JS-app і Vencon). Rozetka на піддомені
-- hard.rozetka.com.ua. Бекфілу нема — новий збір. Forward-only, ідемпотентно.

-- Апостроф — ʼ (U+02BC), не SQL-лапка: інакше екранування '' ламає регекс тесту
-- catalog-meta ([^']+ зупиняється на подвоєній лапці й slug лишається «незасіяним»).
INSERT INTO category (name, slug) VALUES
  ('Оперативна памʼять', 'ram')
ON CONFLICT (slug) DO NOTHING;
