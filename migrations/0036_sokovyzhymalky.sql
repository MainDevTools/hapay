-- 0036: нова категорія СОКОВИЖИМАЛКИ (дрібна кухня).
--
-- Добрий матчер: бренд+модель (GORENJE JC805E, Philips HR1836/00, Tefal ZE370138) →
-- extract_mpn 50-58%, 20 ключів у 2+ крамницях (заміряно 2026-07-22).
--
-- 7 appliance-крамниць (Citrus пропущено — гаджетний профіль). Rozetka на bt-піддомені.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Соковижималки', 'sokovyzhymalky')
ON CONFLICT (slug) DO NOTHING;
