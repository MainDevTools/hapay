-- 0057: нова категорія ШЛІФМАШИНИ (орбітальні/стрічкові/вібраційні) (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні → extract_mpn дробить. Per-store історія повна.
--
-- ⚠ Окремо від болгарок (0052): це ПЛОСКО-шліфувальні (не кутові). 5 крамниць:
--   · Epicentr shlifovalnye-i-polirovalnye-mashiny, Moyo shlifmashinyi, Allo shlifmashiny,
--     Comfy grinders — окремі від їхніх болгарок;
--   · Foxtrot — беремо grinders_lentochnye (стрічкові): широкий grinders.html на 55% болгарки
--     (дублював би 0052), а стрічкові — 0% болгарок;
--   · Rozetka (c152503) / Eldorado (c1284670) ПРОПУЩЕНО — це та сама широка категорія, що вже
--     віддана болгаркам 0052 (100% колізія).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Шліфмашини', 'shlifmashyny')
ON CONFLICT (slug) DO NOTHING;
