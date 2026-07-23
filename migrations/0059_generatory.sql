-- 0059: нова категорія ГЕНЕРАТОРИ (електрогенератори) (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні (Konner&Sohnen, Graphite 58G904) → extract_mpn дробить. Per-store історія повна.
-- Верифіковано 2026-07-23: Epicentr 60/60, Foxtrot 38/42, Moyo 24/24.
--
-- 6 крамниць (Allo-URL не знайдено — пропущено, можна дописати згодом). Rozetka на головному
-- домені. Moyo під stacionarnoe_oborudo. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Генератори', 'generatory')
ON CONFLICT (slug) DO NOTHING;
