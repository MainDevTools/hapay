-- 0074: нова категорія АВТОКОМПРЕСОРИ (Авто) — 12V насоси для підкачки шин.
--
-- ⚠ Слабкий cross-store матчер (короткі коди: Vitol K-72, VOIN VL-720, URAGAN 90135) →
-- extract_mpn бере непослідовно. АЛЕ бренд-збіг помітний (URAGAN — і Foxtrot, і Epicentr).
-- Per-store історія повна. Верифіковано 2026-07-23: Foxtrot 42/42, Epicentr 60/60, Allo 58/60.
--
-- Окремо від DIY-компресорів (0058 — стаціонарні поршневі). 6 крамниць. Rozetka авто на
-- піддомені auto.rozetka.com.ua. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Автокомпресори', 'avtokompresory')
ON CONFLICT (slug) DO NOTHING;
