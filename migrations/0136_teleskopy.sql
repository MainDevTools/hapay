-- 0136: нова категорія ТЕЛЕСКОПИ (Оптика).
--
-- Матчер заміряно 2026-07-24: Оптика. Allo 5/60 + Epicentr 8/60 + Rozetka c89847. 3 СПІЛЬНІ ключі (Bresser/Levenhuk перетинаються) — слабко-середній.
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Телескопи', 'teleskopy')
ON CONFLICT (slug) DO NOTHING;
