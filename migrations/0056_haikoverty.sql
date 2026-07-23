-- 0056: нова категорія ГАЙКОВЕРТИ (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні (Bosch GDS 18V-400, DeWalt) → extract_mpn дробить. Per-store історія повна.
-- Верифіковано 2026-07-23: Epicentr/Rozetka/Foxtrot/Moyo мають ОКРЕМІ гайковерт-категорії.
--
-- ⚠ 4 крамниці. Eldorado/Comfy/Allo тримають гайковерти як ФАСЕТ шуруповертів (той самий
-- лістинг, що вже збираємо 0050) — пропущено, щоб не дублювати товар. Rozetka на головному
-- домені. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Гайковерти', 'haikoverty')
ON CONFLICT (slug) DO NOTHING;
