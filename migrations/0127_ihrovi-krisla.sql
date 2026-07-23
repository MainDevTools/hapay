-- 0127: нова категорія ІГРОВІ КРІСЛА — старт розділу «Геймінг».
--
-- ⚠ ОДНЕ джерело: Rozetka c4657827 (чиста геймерська категорія, пошук-URL).
-- Allo/Epicentr слаги не знайдено за 2 хвилі здогадів — зупинились за гальмами.
-- Розділ «Геймінг» також приймає переноси konsoli/geympady/kylymky (taxonomy-UI,
-- без міграцій). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Ігрові крісла', 'ihrovi-krisla')
ON CONFLICT (slug) DO NOTHING;
