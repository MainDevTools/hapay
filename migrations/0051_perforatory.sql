-- 0051: нова категорія ПЕРФОРАТОРИ (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні (Bosch GBH 2-26 DRE, Makita HR2470) → extract_mpn дробить. Per-store історія
-- цін повна. Окремо від шуруповертів (0050): SDS rotary hammers. Верифіковано 2026-07-23
-- — усі 4 fetch-крамниці повертають перфоратори (Foxtrot 39/42, Moyo/Allo/Epicentr 60/60).
--
-- 7 крамниць. Rozetka на головному домені (rock_drills). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Перфоратори', 'perforatory')
ON CONFLICT (slug) DO NOTHING;
