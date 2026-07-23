-- 0103: нова категорія ФІТНЕС-БРАСЛЕТИ (Електроніка).
--
-- ✓ СИЛЬНИЙ cross-store матчер — кілька домінантних моделей усюди (Xiaomi Smart Band 10,
-- Samsung Galaxy Fit 3, Amazfit, Huawei Band). Заміряно 2026-07-23: extract_mpn Foxtrot
-- 19/22, Allo 22/57, Epicentr 7/60 → 18 спільних ключів у 2+ крамницях. Per-store історія
-- повна. (Приклад «мало ходових моделей → сильний», на відміну від powerbank 0104.)
--
-- Окремо від смарт-годинників (smart-hodynnyky). 6 крамниць (Moyo не знайдено). Rozetka на
-- головному домені (fitnes-trekery). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Фітнес-браслети', 'fitnes-braslety')
ON CONFLICT (slug) DO NOTHING;
