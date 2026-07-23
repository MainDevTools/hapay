-- 0119: нова категорія ЗАРЯДНІ СТАНЦІЇ — старт розділу «Енергія» (автономність).
--
-- Найгарячіша вертикаль ринку (EcoFlow/Bluetti/Anker/Marstek), преміум-ціни —
-- профіль для Omnibus. Матчер заміряно 2026-07-23: слабко-СЕРЕДНІЙ — 4 спільні
-- ключі у 2+ джерелах з 5 заміряних (Allo 11/60, Moyo 17/24, Epicentr 8/60,
-- Foxtrot 17/42, DniproM 0/11 — descriptive «Система резервного живлення»).
-- 7 джерел: Allo/Moyo/Epicentr/Foxtrot/DniproM (верифіковано парсингом) +
-- Rozetka c4674585 і Comfy charging-stations (render/пошук-URL, довіра як
-- усталено). ⚠ НЕ плутати з zaryadnye-stantsii-dlya-elektromobiley (EV-чарджери).
-- Розділ «Енергія» також приймає переноси: dbzh (з Електроніки), generatory
-- (з Інструментів) — без міграцій, лише taxonomy-UI.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Зарядні станції', 'zaryadni-stantsiyi')
ON CONFLICT (slug) DO NOTHING;
