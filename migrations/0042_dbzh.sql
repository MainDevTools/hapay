-- 0042: нова категорія ДБЖ (джерела безперебійного живлення).
--
-- Середній матчер: бренд+модель (POWERCOM RPT-2000AP, APC Smart-UPS SMC3000RMI2U, Eaton
-- 5E G2) → extract_mpn 53-88%, 8 ключів у 2+ крамницях (заміряно 2026-07-23). Частина —
-- роутерні міні-UPS, що різняться; звідси перетин помірний.
--
-- 6 крамниць (Foxtrot/Telemart/Epicentr/Moyo/Rozetka/KTC). Rozetka на hard-піддомені.
-- ⚠ НЕ плутати з БЖ (блоки живлення ПК, 0029) — це джерела БЕЗПЕРЕБІЙНОГО живлення.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('ДБЖ', 'dbzh')
ON CONFLICT (slug) DO NOTHING;
