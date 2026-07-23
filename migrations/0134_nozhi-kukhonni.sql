-- 0134: нова категорія КУХОННІ НОЖІ (Кухня).
--
-- Матчер заміряно 2026-07-24: Кухня. Allo 15/60 (парсингом) + Rozetka c4626670; Epicentr kukhonnye-nozhi-i-nabory не пройшов поріг релевантності — пропуск.
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Кухонні ножі', 'nozhi-kukhonni')
ON CONFLICT (slug) DO NOTHING;
