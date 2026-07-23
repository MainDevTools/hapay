-- 0060: нова категорія МИЙКИ ВИСОКОГО ТИСКУ (мінімийки) (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050), АЛЕ тут краще за
-- середню: Karcher/Bosch кодують модель чіткіше (Karcher K 3/K 5/K 7, Bosch EasyAquatak
-- 100) — ті самі моделі між крамницями. Per-store історія повна. Верифіковано 2026-07-23:
-- Foxtrot 42/42, Epicentr 60/60.
--
-- 5 крамниць (Allo/Moyo-URL не знайдено — пропущено). Rozetka на головному домені (cleaners).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Мийки високого тиску', 'myyky')
ON CONFLICT (slug) DO NOTHING;
