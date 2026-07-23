-- 0138: нова категорія ГІТАРИ (Музика).
--
-- Матчер заміряно 2026-07-24: Музика. Allo 4/60 + Epicentr 3/60 + Rozetka c4628348. Спільних 0 — descriptive-назви (розмір/колір).
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Гітари', 'hitary')
ON CONFLICT (slug) DO NOTHING;
