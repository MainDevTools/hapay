-- 0045: нова категорія ЕЛЕКТРОБРИТВИ (персональний догляд).
--
-- Середній матчер: ті самі моделі Philips/Braun перетинаються між крамницями (PHILIPS
-- S5885/10 і у Foxtrot, і в Moyo) → 14 ключів у 2+ крамницях, хоч extract_mpn і нижчий
-- (25-33%, бо суфікс «/10» не завжди береться) — заміряно 2026-07-23.
--
-- 7 appliance-крамниць (Foxtrot/Moyo/Allo/Epicentr/Comfy/Rozetka/Eldorado). Rozetka на
-- bt-піддомені. Лише електробритви (не станки). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Електробритви', 'brytvy')
ON CONFLICT (slug) DO NOTHING;
