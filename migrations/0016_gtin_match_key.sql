-- 0016: GTIN — глобальний ідентифікатор товару для крос-крамничного матчингу (2026-07-22).
--
-- Досі товари зіставлялись лише за MPN із назви (T15). Матчинг за назвою впирався в
-- стелю (T17): крамниці електроніки штрихкодів не публікують, тож ключем лишався
-- тендітний артикул. Аптеки/медтовари віддають GTIN (штрихкод EAN/UPC) для КОЖНОГО
-- товару — глобальний код на коробці, надійніший за назву за побудовою.
--
-- Додаємо:
--   `gtin`       — канонічний GTIN-14; пише pick_gtin(it.gtins) при персисті.
--   `match_key`  — ГЕНЕРОВАНИЙ COALESCE(gtin, mpn): єдиний ключ «той самий товар».
--                  GTIN перемагає, MPN — запасний. Групування (api/db.py) ходить по
--                  ньому замість mpn.
--
-- Чому STORED generated, а не звичайна колонка: перераховується САМ при зміні gtin/mpn,
-- тож не може розійтися з ними (той самий прийом, що й у title_tsv). Персист про
-- match_key не знає — пише лише gtin.
--
-- ЕЛЕКТРОНІКУ НЕ ЧІПАЄ: там gtin завжди NULL → match_key = mpn, усі наявні групи
-- незмінні. Доведено: у store_product зараз 0 рядків із gtin, тож match_key ≡ mpn
-- для всього поточного каталогу.
--
-- Форвардна й ідемпотентна: IF NOT EXISTS (§6.6).

ALTER TABLE store_product ADD COLUMN IF NOT EXISTS gtin TEXT;

ALTER TABLE store_product ADD COLUMN IF NOT EXISTS match_key TEXT
    GENERATED ALWAYS AS (COALESCE(gtin, mpn)) STORED;

-- Покриває всі шляхи групування (gkey, offers_n, product_offers, канонічність плитки).
CREATE INDEX IF NOT EXISTS ix_sp_match_key ON store_product (match_key);
