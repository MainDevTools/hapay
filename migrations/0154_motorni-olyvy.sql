-- 0154: нова категорія МОТОРНІ ОЛИВИ (Авто).
--
-- Матчер заміряно 2026-07-24: Epicentr 0/60 (в'язкість «5W-30» + літраж —
-- варіантні назви). 2 джерела: Epicentr motornye-masla (парсингом) + Rozetka
-- motornie-masla c4659575 (пошук-URL). Per-store Omnibus.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Моторні оливи', 'motorni-olyvy')
ON CONFLICT (slug) DO NOTHING;
