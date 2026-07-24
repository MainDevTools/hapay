-- 0147: нова категорія РАЦІЇ — старт розділу «Зв'язок і навігація».
--
-- Воєнний попит, стрибучі ціни — сильний Omnibus-профіль. Матчер заміряно
-- 2026-07-24: Allo 6/60 + Epicentr 10/60 (Baofeng-домінанта ОБИДВА, але 0
-- спільних: версійність UV-82 vs BF-888s + бандли «+ Гарнітура» ламають ключ).
-- 3 джерела: Allo products/radiostancii + Epicentr ratsii (парсингом) +
-- Rozetka walkie-talkie c84018 (пошук-URL).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Рації', 'ratsii')
ON CONFLICT (slug) DO NOTHING;
