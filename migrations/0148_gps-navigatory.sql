-- 0148: нова категорія GPS-НАВІГАТОРИ (Зв'язок).
--
-- Матчер заміряно 2026-07-24: Epicentr 6/55, чистота 41/55 (75% — верхівку
-- засмічують HUD-спідометри; прийнято з приміткою, Garmin глибше в лістингу).
-- 2 джерела: Epicentr gps-navigatory (парсингом) + Rozetka auto-піддомен
-- gps-navigators c80047 (пошук-URL; host-політика auto. пропускає). Allo
-- слаги не знайдено за 2 хвилі.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('GPS-навігатори', 'gps-navigatory')
ON CONFLICT (slug) DO NOTHING;
