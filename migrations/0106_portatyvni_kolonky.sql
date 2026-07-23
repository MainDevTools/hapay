-- 0106: нова категорія ПОРТАТИВНІ КОЛОНКИ (Bluetooth-акустика) (Електроніка).
--
-- ⚠ Weak-medium матчер (слабше за прогноз): преміум збігається (JBL Charge, Sony, Marshall,
-- Xiaomi), АЛЕ довгий хвіст дешевих (Hopestar, W-King, Remax, HISENSE PARTY) розмиває.
-- Заміряно 2026-07-23: extract_mpn Foxtrot 18/42, Allo 40/60 → лише 4 спільні ключі у 2+.
-- Per-store історія повна.
--
-- Окремо від навушників/audio та ПК-акустики. 3 крамниці (Rozetka/Foxtrot/Allo). Rozetka
-- на головному домені (portativnie-kolonki). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Портативні колонки', 'portatyvni-kolonky')
ON CONFLICT (slug) DO NOTHING;
