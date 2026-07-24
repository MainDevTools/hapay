-- 0149: нова категорія КОТУШКИ РИБАЛЬСЬКІ — старт розділу «Риболовля».
--
-- Матчер заміряно 2026-07-24: Epicentr 3/60 (дешевий Cobra-тайл зверху;
-- Shimano/Daiwa глибше). 2 джерела: Epicentr rybolovnye-katushki (парсингом)
-- + Rozetka reels c84712 (пошук-URL). Per-store Omnibus.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Котушки рибальські', 'kotushky-rybalski')
ON CONFLICT (slug) DO NOTHING;
