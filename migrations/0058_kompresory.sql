-- 0058: нова категорія КОМПРЕСОРИ (повітряні) (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні (Einhell TE-AC 24, Fubag) → extract_mpn дробить. Per-store історія повна.
-- Верифіковано 2026-07-23: Epicentr 60/60, Allo 59/60, Moyo 24/24.
--
-- 5 крамниць (Comfy/Eldorado компресори не тримають — пропущено). Rozetka на головному
-- домені. Moyo під stacionarnoe_oborudo. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Компресори', 'kompresory')
ON CONFLICT (slug) DO NOTHING;
