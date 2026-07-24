-- 0159: «Наш вибір» v1 (S9) — довідники + ваги формули.
--
-- delivery_rule / store_network — РУЧНІ довідники (сіються окремо, лише виписане
-- з першоджерел-сторінок умов крамниць із датою: [здогад] заборонено — тому тут
-- ПОРОЖНІ; відсутність запису = no_delivery_data, доставка в скорі 0).
-- choice_weights — патерн detection_config: ваги міняються без деплою коду.
-- Ваги 0.70/0.25/0.05 і alpha=1 затверджені оператором 2026-07-24 («ваги ок»).

CREATE TABLE IF NOT EXISTS delivery_rule (
    source_id         BIGINT PRIMARY KEY REFERENCES source(source_id),
    free_from_kop     BIGINT,                -- NULL = безкоштовної межі нема
    base_delivery_kop BIGINT NOT NULL,
    np                BOOLEAN NOT NULL DEFAULT true,
    courier           BOOLEAN NOT NULL DEFAULT false,
    note              TEXT,                  -- звідки виписано + дата звірки
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS store_network (
    source_id   BIGINT PRIMARY KEY REFERENCES source(source_id),
    has_pickup  BOOLEAN NOT NULL DEFAULT false,
    cities_note TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS choice_weights (
    choice_weights_id BIGSERIAL PRIMARY KEY,
    w_price       NUMERIC(4,2) NOT NULL,
    w_honesty     NUMERIC(4,2) NOT NULL,
    pickup_bonus  NUMERIC(4,2) NOT NULL,
    laplace_alpha NUMERIC(4,2) NOT NULL DEFAULT 1,
    valid_from    TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to      TIMESTAMPTZ
);

INSERT INTO choice_weights (w_price, w_honesty, pickup_bonus, laplace_alpha)
SELECT 0.70, 0.25, 0.05, 1
WHERE NOT EXISTS (SELECT 1 FROM choice_weights);
