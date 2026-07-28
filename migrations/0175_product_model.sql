-- 0175: канонічна МОДЕЛЬ товару поверх сторінок крамниць (S30)
--
-- Проблема, заміряна 2026-07-28:
--   56 623 рядки `store_product` — це сторінки КРАМНИЦЬ, не товари.
--   5 195 моделей продаються у 2+ крамницях і займають 16 773 рядки.
--   Один і той самий телефон — п'ять окремих записів: п'ять разів у фіді знижень,
--   порівняння працює зі «сторінкою крамниці», а «найнижча ціна на цю модель»
--   узагалі не є поняттям у моделі даних.
--
-- ⚠ ЧОГО ЦЯ ТАБЛИЦЯ НЕ РОБИТЬ — і це юридично важливо.
-- Детекція знижки лишається ПОСТОРІНКОВОЮ. Стаття закону №3153-IX говорить про
-- найнижчу ціну за 30 днів У ЦЬОГО ПРОДАВЦЯ; «модельний» мінімум по всіх крамницях
-- статутною базою НЕ є і бейджем стати не може. Модель існує для ПОРІВНЯННЯ
-- (де дешевше, скільки пропозицій), детекція — для однієї сторінки. Змішати їх
-- означало б винести вердикт, якого закон не передбачає.
--
-- ⚠ ЧОМУ 48% ЛИШАЮТЬСЯ БЕЗ МОДЕЛІ.
-- `match_key` — генерована колонка COALESCE(gtin, mpn) (0016), і для 27 223 рядків
-- вона порожня: у назві немає ні GTIN, ні артикула. Створювати їм по «моделі з одного
-- рядка» — це 27 тисяч записів, які нічого не групують і лише роздувають таблицю.
-- Тому `product_id` там NULL, а інтерфейс падає назад на сторінку крамниці.
-- Зменшення цих 48% — окрема робота (нечіткий матчинг), не ця міграція.

CREATE TABLE IF NOT EXISTS product (
  product_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  match_key   TEXT NOT NULL UNIQUE,
  title       TEXT NOT NULL,
  category_id BIGINT REFERENCES category(category_id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE product IS
  'Канонічна модель: те, що продають у кількох крамницях під одним артикулом. '
  'Ключ — match_key (GTIN або MPN). Детекція знижок ЛИШАЄТЬСЯ посторінковою.';

ALTER TABLE store_product ADD COLUMN IF NOT EXISTS product_id BIGINT
  REFERENCES product(product_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_sp_product ON store_product (product_id)
  WHERE product_id IS NOT NULL;

-- ── самопідтримка ────────────────────────────────────────────────────────────────
-- Тригером, а не періодичним джобом: джоб додає питання «коли він востаннє ходив»,
-- і саме на цьому класі помилок ми обпеклись 28.07 (бекап був `enabled`, але не
-- виконувався). Тригер не має стану, який можна забути запустити.
--
-- Канонічна назва — НАЙКОРОТША в групі: маркетинговий хвіст («Офіційна гарантія!
-- Найкраща ціна») лише подовжує рядок, тож коротша назва майже завжди ближча до
-- самого товару. Правило детерміноване й пояснюване — на відміну від «назви з
-- найдешевшої крамниці», яка стрибала б за цінами.
CREATE OR REPLACE FUNCTION trg_sp_link_product() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  pid BIGINT;
BEGIN
  IF NEW.match_key IS NULL THEN
    NEW.product_id := NULL;
    RETURN NEW;
  END IF;

  INSERT INTO product (match_key, title, category_id)
       VALUES (NEW.match_key, NEW.title, NEW.category_id)
  ON CONFLICT (match_key) DO UPDATE
     SET title = CASE WHEN length(EXCLUDED.title) < length(product.title)
                      THEN EXCLUDED.title ELSE product.title END
  RETURNING product_id INTO pid;

  NEW.product_id := pid;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS sp_link_product ON store_product;
CREATE TRIGGER sp_link_product
  BEFORE INSERT OR UPDATE OF match_key, title ON store_product
  FOR EACH ROW EXECUTE FUNCTION trg_sp_link_product();

-- ── бекфіл наявних рядків ────────────────────────────────────────────────────────
-- Спершу моделі (найкоротша назва в групі), тоді звʼязок. Одним проходом, бо
-- 29 400 рядків — це секунди, а не година.
INSERT INTO product (match_key, title, category_id)
SELECT DISTINCT ON (match_key) match_key, title, category_id
  FROM store_product
 WHERE match_key IS NOT NULL
 ORDER BY match_key, length(title), store_product_id
ON CONFLICT (match_key) DO NOTHING;

UPDATE store_product sp
   SET product_id = p.product_id
  FROM product p
 WHERE sp.match_key = p.match_key
   AND sp.product_id IS DISTINCT FROM p.product_id;
