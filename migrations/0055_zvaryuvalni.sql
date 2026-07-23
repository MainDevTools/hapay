-- 0055: нова категорія ЗВАРЮВАЛЬНІ АПАРАТИ (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні (DWT MMA-320 E, Tekhmann TWI-305 MIG, Vitals MMA-1400) → extract_mpn дробить.
-- Per-store історія цін повна. Верифіковано 2026-07-23: Foxtrot/Epicentr/Allo/Moyo — усі
-- 100% зварювального профілю.
--
-- 6 крамниць (Comfy зварювання не тримає — пропущено). Rozetka на головному домені. Moyo
-- зварювання під stacionarnoe_oborudo (не electroinstrument). Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Зварювальні апарати', 'zvaryuvalni')
ON CONFLICT (slug) DO NOTHING;
