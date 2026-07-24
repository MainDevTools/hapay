-- 0165: характеристики з карток товарів (S12).
--
-- Інваріант B5 розширено оператором 2026-07-24: до «лише фактів» додано
-- ХАРАКТЕРИСТИКИ — пари назва-значення технічних фактів зі спец-таблиць, завжди з
-- провенансом (крамниця+URL+дата). Описи (зв'язний текст) не зберігаються ані байта —
-- guard на рівні clean_attrs (задовге значення відкидається цілком, не обрізається).
--
-- Одна картка на крос-групу (специфікації спільні для того самого товару);
-- прив'язка до store_product_id (не match_key — той мутує при бекфілах mpn).
-- Довідник ПЕРЕЗАПИСУВАНИЙ (не історія цін): повторний збір заміняє набір.

CREATE TABLE product_spec (
    spec_id          BIGSERIAL PRIMARY KEY,
    store_product_id BIGINT NOT NULL UNIQUE
                     REFERENCES store_product (store_product_id) ON DELETE CASCADE,
    source_url       TEXT NOT NULL,
    collected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE spec_attr (
    spec_id  BIGINT NOT NULL REFERENCES product_spec (spec_id) ON DELETE CASCADE,
    position INT NOT NULL,
    name     TEXT NOT NULL,
    value    TEXT NOT NULL,
    PRIMARY KEY (spec_id, position)
);
