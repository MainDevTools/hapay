-- 0122: нова категорія РОЗУМНІ РОЗЕТКИ (Розумний дім).
--
-- Матчер заміряно 2026-07-24: слабкий (Allo 10/60; дрібні бренди Tuya/Nous/
-- LDNIO, descriptive-назви). 2 джерела: Allo (парсингом) + Rozetka c4638455
-- (пошук-URL). Citrus має категорію, але його plain-GET віддає «популярне»
-- замість категорії (урок Citrus-GPU) — НЕ реєструємо. Foxtrot мішає розетки
-- з датчиками (smart_rozetki_i_datchiki) — теж пропуск.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Розумні розетки', 'rozumni-rozetky')
ON CONFLICT (slug) DO NOTHING;
