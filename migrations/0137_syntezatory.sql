-- 0137: нова категорія СИНТЕЗАТОРИ (старт розділу «Музика»).
--
-- Матчер заміряно 2026-07-24: старт розділу «Музика». Allo 18/60 (Casio/Yamaha коди) + Rozetka c286764; Epicentr категорії нема. Спільних 0 (1 парсинг-джерело).
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Синтезатори', 'syntezatory')
ON CONFLICT (slug) DO NOTHING;
