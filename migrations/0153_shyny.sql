-- 0153: нова категорія ШИНИ (Авто) — сезонна вертикаль перед зміною гуми.
--
-- Матчер заміряно 2026-07-24: Epicentr 1/60 — розмірні коди «175/70R13»
-- extract_mpn не бере (відомий клас обмеження) → per-store Omnibus (сезонні
-- «знижки» на гуму — класика накачаних). 2 джерела: Epicentr avtoshiny
-- (парсингом) + Rozetka auto-піддомен avtoshiny c4330821 (пошук-URL).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Шини', 'shyny')
ON CONFLICT (slug) DO NOTHING;
