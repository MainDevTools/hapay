-- 0141: нова категорія КОТЛИ ГАЗОВІ — старт розділу «Опалення» (сезонний пік).
--
-- Матчер заміряно 2026-07-24: 2 спільні ключі (Epicentr 6/60 + Vencon 3/27;
-- Baxi/Protherm перетинаються). 3 джерела: Epicentr + Vencon (парсингом) +
-- Rozetka bt/kotly-gazovye c117206 (пошук-URL). Електрокотли — окрема
-- майбутня категорія, не мішаємо. Per-store Omnibus цінний (чеки високі).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Котли газові', 'kotly-hazovi')
ON CONFLICT (slug) DO NOTHING;
