-- 0044: нова категорія ФЕНИ — старт вертикалі «персональний догляд» (новий розділ
-- «Краса і догляд»).
--
-- Добрий матчер: чистий SKU у назві (PHILIPS HPS910/00, BHD839/00, ROWENTA CV...) →
-- extract_mpn 70-86%, 26 ключів у 2+ крамницях (заміряно 2026-07-23) — поряд із чайниками/GPU.
--
-- 7 appliance-крамниць (Foxtrot/Moyo/Allo/Epicentr/Comfy/Rozetka/Eldorado; Citrus —
-- гаджетний профіль). Rozetka на bt-піддомені. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Фени', 'feny')
ON CONFLICT (slug) DO NOTHING;
