-- 0145: нова категорія ШВЕЙНІ МАШИНИ — старт розділу «Шиття».
--
-- Матчер заміряно 2026-07-24: Epicentr 6/60 (FHSM/дешевий тайл; Janome/Brother
-- глибше в лістингу); Allo слаги не знайдено за 2 хвилі. 3 джерела: Epicentr
-- shveynaya-tekhnika (мішає ~5/60 оверлоків — як ділить крамниця) + Rozetka bt
-- sewing_machines c80159 + Eldorado c1039042 (render, пошук-URL).
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Швейні машини', 'shveyni-mashyny')
ON CONFLICT (slug) DO NOTHING;
