-- 0140: нова категорія ФІЛАМЕНТ ДЛЯ 3D-ДРУКУ (3D-друк).
--
-- Матчер заміряно 2026-07-24: 3D-друк. ⚠ ОДНЕ джерело: Rozetka c4671751 (пошук-URL); Allo/Epicentr слаги не знайдено за 2 хвилі — гальма. Витратка до 0139, варіантність тип+колір.
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Філамент для 3D-друку', 'filament-3d')
ON CONFLICT (slug) DO NOTHING;
