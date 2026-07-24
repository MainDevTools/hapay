-- 0144: нова категорія НАСТІЛЬНІ ІГРИ (Іграшки).
--
-- Матчер заміряно 2026-07-24: MAUDAU 13/48; назви-титули ігор (без кодів) →
-- слабкий крос очікувано. 2 джерела: MAUDAU (парсингом) + Rozetka
-- nastoljnye-igry-i-golovolomki c98280 (пошук-URL); Antoshka слаг не
-- знайдено за 2 хвилі. Per-store Omnibus повний.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Настільні ігри', 'nastilni-ihry')
ON CONFLICT (slug) DO NOTHING;
