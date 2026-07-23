-- 0133: нова категорія СКОВОРІДКИ (старт розділу «Кухня»).
--
-- Матчер заміряно 2026-07-24: старт розділу «Кухня». Allo 40/60 (Tefal-коди!) + Epicentr 4/60 + Rozetka c4626754. Спільних 0 — тайли.
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Сковорідки', 'skovorody')
ON CONFLICT (slug) DO NOTHING;
