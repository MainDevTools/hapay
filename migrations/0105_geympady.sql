-- 0105: нова категорія ГЕЙМПАДИ (Електроніка).
--
-- ⚠ Weak-medium матчер (слабше за прогноз): преміум збігається (Sony DualSense, Xbox
-- Wireless Controller), АЛЕ довгий хвіст дешевих (GAMEPRO MG650B, IPEGA, GamePro) розмиває.
-- Заміряно 2026-07-23: extract_mpn Foxtrot 11/42, Allo 18/60 → лише 3 спільні ключі у 2+.
-- Per-store історія повна.
--
-- 3 крамниці (Rozetka/Foxtrot/Allo; Epicentr слаг 404). Rozetka на головному домені
-- (djoysticks). Allo — фасет aksessuary-k-igrovym-pristavkam. Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Геймпади', 'geympady')
ON CONFLICT (slug) DO NOTHING;
