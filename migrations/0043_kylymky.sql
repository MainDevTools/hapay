-- 0043: нова категорія КИЛИМКИ ДЛЯ МИШІ (периферія ПК).
--
-- ⚠ СЛАБКИЙ матчер: аксесуар із брендово-описовою назвою (HATOR Tonn EVO M, EVOLVE
-- OnePad XL) → extract_mpn 40-50%, лише 3 ключі у 2+ крамницях (заміряно 2026-07-23).
-- Полиця для перегляду, дешевий аксесуар.
--
-- 6 крамниць (Foxtrot/Rozetka/Telemart/Brain/Moyo/Epicentr). Rozetka на hard-піддомені.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Килимки для миші', 'kylymky')
ON CONFLICT (slug) DO NOTHING;
