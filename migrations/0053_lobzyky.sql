-- 0053: нова категорія ЕЛЕКТРОЛОБЗИКИ (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні (Bosch PST 800 PEL, Makita 4329) → extract_mpn дробить. Per-store історія цін
-- повна. Верифіковано 2026-07-23: Foxtrot 42/42, Epicentr 60/60 — лобзики.
--
-- 7 крамниць. Rozetka на головному домені (jigsaws). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Електролобзики', 'lobzyky')
ON CONFLICT (slug) DO NOTHING;
