-- 0001_init.sql — уся v2.1-схема (§6), ЧИСТИЙ PostgreSQL (Neon-сумісний, free-forever).
-- Timescale-фічі (hypertable / continuous aggregate / компресія) — SCALE-upgrade, винесено в
-- 0002_timescale.sql (застосовується, коли обсяг цього вимагатиме; §6.6). MVP-валідація їх не потребує:
-- price_snapshot — звичайна таблиця з покривним індексом; графік читає сирі точки (§9.2).
-- Раннер (db/migrate.py) виконує це у simple-protocol (працює і для plain PG).

-- ─────────────────────────── §6.2 Джерела та таксономія ───────────────────────────
CREATE TABLE source (
  source_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name             TEXT NOT NULL,
  base_url         TEXT NOT NULL,
  discount_url     TEXT,
  platform         TEXT CHECK (platform IN
                     ('horoshop','opencart','woocommerce','magento','bitrix','custom')),
  adapter_kind     TEXT NOT NULL CHECK (adapter_kind IN
                     ('ssr','cookie_challenge','headless','json_api')),
  fetch_tier       TEXT CHECK (fetch_tier IN ('A','B','C')),
  preferred_method TEXT,
  discovery_cron   TEXT,
  baseline_cron    TEXT,
  robots_checked_at TIMESTAMPTZ,
  frozen_at        TIMESTAMPTZ,
  active           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (base_url)
);

CREATE TABLE category (
  category_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  parent_id   BIGINT REFERENCES category(category_id),
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE
);

CREATE TABLE source_category_map (
  source_category_map_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id     BIGINT NOT NULL REFERENCES source(source_id),
  store_category_path TEXT NOT NULL,
  listing_url   TEXT,
  track_baseline BOOLEAN NOT NULL DEFAULT FALSE,
  category_id   BIGINT NOT NULL REFERENCES category(category_id),
  UNIQUE (source_id, store_category_path)
);

-- ─────────────────────────── §6.3 Товар і історія цін ───────────────────────────
CREATE TABLE store_product (
  store_product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id     BIGINT NOT NULL REFERENCES source(source_id),
  external_ref  TEXT NOT NULL,
  url           TEXT NOT NULL,
  title         TEXT NOT NULL,
  image_url     TEXT,
  image_blurhash TEXT,
  image_source  TEXT CHECK (image_source IS NULL OR image_source IN ('feed','hotlink')),
  category_id   BIGINT NOT NULL REFERENCES category(category_id),
  variant_note  TEXT,
  needs_variant_resolution BOOLEAN NOT NULL DEFAULT FALSE,
  variant_resolved_at TIMESTAMPTZ,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  title_tsv     tsvector GENERATED ALWAYS AS (to_tsvector('simple', title)) STORED,
  UNIQUE (source_id, external_ref)
);
CREATE INDEX ix_sp_cat ON store_product (category_id);
CREATE INDEX ix_sp_fts ON store_product USING GIN (title_tsv);

CREATE TABLE canary (
  canary_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id        BIGINT NOT NULL REFERENCES source(source_id),
  url              TEXT NOT NULL,
  expected_min_kop BIGINT NOT NULL,
  expected_max_kop BIGINT NOT NULL,
  reviewed_at      TIMESTAMPTZ,
  note             TEXT
);

CREATE TABLE http_cache (
  url           TEXT PRIMARY KEY,
  etag          TEXT,
  last_modified TEXT,
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scan_run (
  scan_run_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id     BIGINT NOT NULL REFERENCES source(source_id),
  surface       TEXT NOT NULL CHECK (surface IN ('discovery','baseline')),
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ,
  status        TEXT NOT NULL CHECK (status IN ('ok','partial','failed','blocked')),
  items_seen    INTEGER NOT NULL DEFAULT 0,
  parse_success_rate DOUBLE PRECISION,
  rejected_anomaly    INTEGER NOT NULL DEFAULT 0,
  rejected_oos        INTEGER NOT NULL DEFAULT 0,
  rejected_currency   INTEGER NOT NULL DEFAULT 0,
  rejected_from_price INTEGER NOT NULL DEFAULT 0,
  rejected_ambiguous  INTEGER NOT NULL DEFAULT 0,
  rejected_declared   INTEGER NOT NULL DEFAULT 0,
  http_note     TEXT
);

-- price_snapshot — APPEND-ONLY факт ціни (звичайна таблиця; hypertable → 0002 scale-upgrade)
CREATE TABLE price_snapshot (
  price_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  store_product_id  BIGINT NOT NULL REFERENCES store_product(store_product_id),
  price_now_kop     BIGINT NOT NULL CHECK (price_now_kop >= 0),
  price_old_kop     BIGINT CHECK (price_old_kop IS NULL OR price_old_kop >= 0),
  in_stock          BOOLEAN NOT NULL DEFAULT TRUE,
  source_method     TEXT,
  seen_at           TIMESTAMPTZ NOT NULL,
  scan_run_id       BIGINT REFERENCES scan_run(scan_run_id),
  is_backfill       BOOLEAN NOT NULL DEFAULT FALSE
);
-- покривний індекс для статутного MIN за 30 днів (§5.2): index-only scan
CREATE INDEX ix_ps_prod_window ON price_snapshot (store_product_id, seen_at)
  INCLUDE (price_now_kop, in_stock);

-- append-only (§6.1): тригер блокує мутації (+ REVOKE — деплой-крок §8.10.1)
CREATE FUNCTION trg_ps_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'price_snapshot append-only (спроба % заблокована)', TG_OP;
END $$;
CREATE TRIGGER trg_ps_no_update BEFORE UPDATE ON price_snapshot
  FOR EACH ROW EXECUTE FUNCTION trg_ps_append_only();
CREATE TRIGGER trg_ps_no_delete BEFORE DELETE ON price_snapshot
  FOR EACH ROW EXECUTE FUNCTION trg_ps_append_only();

-- ─────────────────────────── §6.4 Подія знижки ───────────────────────────
CREATE TABLE discount_event (
  discount_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  store_product_id  BIGINT NOT NULL REFERENCES store_product(store_product_id),
  announce_date     DATE NOT NULL,
  current_kop       BIGINT NOT NULL,
  old_declared_kop  BIGINT,
  declared_pct      INTEGER,
  reference_kop     BIGINT,
  verified_pct      INTEGER,
  badge_state       TEXT NOT NULL CHECK (badge_state IN
                      ('declared','verified','verified_provisional','pumped','insufficient_history')),
  ended_at          TIMESTAMPTZ,
  computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (store_product_id, announce_date)
);
CREATE INDEX ix_de_state ON discount_event (badge_state, computed_at);
CREATE INDEX ix_de_prod  ON discount_event (store_product_id);

-- ─────────────────────────── §6.5 Watchlist / алерти / конфіг ───────────────────────────
CREATE TABLE watchlist (
  watchlist_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tg_user_id    BIGINT NOT NULL,
  kind          TEXT NOT NULL CHECK (kind IN ('category','store_product','query')),
  ref_id        BIGINT,
  query_text    TEXT,
  min_verified_pct INTEGER DEFAULT 5,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_wl_user ON watchlist (tg_user_id);

CREATE TABLE alert_log (
  alert_log_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  watchlist_id  BIGINT REFERENCES watchlist(watchlist_id),
  discount_event_id BIGINT REFERENCES discount_event(discount_event_id),
  badge_state   TEXT NOT NULL,
  shown_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (watchlist_id, discount_event_id, badge_state)
);

CREATE TABLE detection_config (
  detection_config_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  window_days        INTEGER NOT NULL DEFAULT 30,
  min_verified_pct   INTEGER NOT NULL DEFAULT 5,
  scan_cadence_per_day INTEGER NOT NULL DEFAULT 2,
  anomaly_factor     DOUBLE PRECISION NOT NULL DEFAULT 5.0,
  step_down_merge    BOOLEAN NOT NULL DEFAULT TRUE,
  parse_success_floor DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  systematic_anomaly_frac DOUBLE PRECISION NOT NULL DEFAULT 0.3,
  min_reference_points INTEGER NOT NULL DEFAULT 10,
  provisional_min_points INTEGER NOT NULL DEFAULT 4,
  declared_ratio_max DOUBLE PRECISION NOT NULL DEFAULT 5.0,
  campaign_gap_days  INTEGER NOT NULL DEFAULT 7,
  announce_confirm_points INTEGER NOT NULL DEFAULT 2,
  exclude_oos_from_window BOOLEAN NOT NULL DEFAULT TRUE,
  valid_from         TIMESTAMPTZ NOT NULL,
  valid_to           TIMESTAMPTZ
);

CREATE TABLE app_config (
  app_config_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  key           TEXT NOT NULL,
  value         TEXT NOT NULL,
  valid_from    TIMESTAMPTZ NOT NULL,
  valid_to      TIMESTAMPTZ
);

-- ─────────────────────────── Сіди (config-дефолти; таксономію — bootstrap §8.10.1) ───────────────────────────
INSERT INTO category (name, slug) VALUES ('Uncategorized', 'uncategorized');

INSERT INTO detection_config (valid_from) VALUES ('2026-01-01T00:00:00Z');

INSERT INTO app_config (key, value, valid_from) VALUES
 ('tz_display','Europe/Kyiv','2026-01-01T00:00:00Z'),
 ('ui_decimal_sep',',','2026-01-01T00:00:00Z'),
 ('ui_thousands_sep',' ','2026-01-01T00:00:00Z'),
 ('csv_bom','1','2026-01-01T00:00:00Z'),
 ('alert_channel','telegram','2026-01-01T00:00:00Z'),
 ('default_category','uncategorized','2026-01-01T00:00:00Z');
