-- 0132: нова категорія ЗМІШУВАЧІ (Сантехніка).
--
-- Матчер заміряно 2026-07-24: Сантехніка. Allo 33/60 + Epicentr 20/60 (парсингом) — спільних 0 (парадокс тайлів: Grohe vs дешеві). Високий per-store MPN.
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Змішувачі', 'zmishuvachi')
ON CONFLICT (slug) DO NOTHING;
