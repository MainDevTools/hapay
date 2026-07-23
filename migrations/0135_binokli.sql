-- 0135: нова категорія БІНОКЛІ (старт розділу «Оптика»).
--
-- Матчер заміряно 2026-07-24: старт розділу «Оптика». Allo 4/60 + Epicentr 7/60 + Rozetka c83917. 1 спільний ключ.
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Біноклі', 'binokli')
ON CONFLICT (slug) DO NOTHING;
