-- 0176: звʼязок «сторінка ↔ модель» — за ключем, без збереженого product_id (S30)
--
-- ⚠ ЧОМУ ПЕРЕРОБКА ЧЕРЕЗ ГОДИНУ ПІСЛЯ 0175.
-- Бекфіл 0175 створив 16 286 моделей і звʼязав з ними РІВНО НУЛЬ сторінок. Причина —
-- у PostgreSQL **BEFORE-тригер не бачить генерованих колонок**: їх обчислюють ПІСЛЯ
-- BEFORE-тригерів, тож усередині мого тригера `NEW.match_key` завжди NULL. Гілка
-- «немає ключа → product_id := NULL» спрацьовувала для КОЖНОГО рядка й затирала
-- звʼязок, який щойно проставив UPDATE.
--
-- Спіймано заміром одразу після деплою (16 286 моделей / 0 звʼязків), не читанням коду.
--
-- Замість лагодити тригер — прибираємо потребу в ньому. `match_key` уже:
--   * генерована колонка (0016) — підтримує себе сама, дрейфувати не може;
--   * УНІКАЛЬНИЙ ключ у `product`;
--   * має індекс `ix_sp_match_key`.
-- Тобто звʼязок уже існує в даних, і збережений `product_id` був лише його копією —
-- зайвою сутністю, яку треба синхронізувати. Найнадійніший синхронізатор — той,
-- якого немає.

DROP TRIGGER IF EXISTS sp_link_product ON store_product;
DROP FUNCTION IF EXISTS trg_sp_link_product();

ALTER TABLE store_product DROP COLUMN IF EXISTS product_id;

-- Назва моделі могла лишитись не найкоротшою, якщо коротший варіант приїхав пізніше:
-- 0175 писав її лише при вставці. Тепер це разова нормалізація, а далі — при кожному
-- зборі (див. `qdb.refresh_models`, який ходить після інджесту).
UPDATE product p
   SET title = best.title
  FROM (SELECT DISTINCT ON (match_key) match_key, title
          FROM store_product WHERE match_key IS NOT NULL
         ORDER BY match_key, length(title), store_product_id) best
 WHERE p.match_key = best.match_key AND p.title IS DISTINCT FROM best.title;

-- Нові моделі, що зʼявились між 0175 і зараз.
INSERT INTO product (match_key, title, category_id)
SELECT DISTINCT ON (match_key) match_key, title, category_id
  FROM store_product
 WHERE match_key IS NOT NULL
 ORDER BY match_key, length(title), store_product_id
ON CONFLICT (match_key) DO NOTHING;
