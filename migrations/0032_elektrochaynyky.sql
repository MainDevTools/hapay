-- 0032: нова категорія ЕЛЕКТРОЧАЙНИКИ — старт вертикалі «дрібна кухня» (рішення оператора).
--
-- Добрий матчер: у назві бренд+модель (GORENJE K15DWBK, Tefal KO200130, Philips HD9318)
-- → extract_mpn 52-79%, 27 ключів у 2+ крамницях (заміряно 2026-07-22) — поряд із БЖ/GPU.
-- Дрібна кухня — appliance-вертикаль: широкий перетин, бо всі 8 appliance-крамниць везуть.
--
-- Листинги у 8 крамницях (appliance: Foxtrot/Moyo/Allo/Epicentr/Comfy/Citrus/Rozetka/
-- Eldorado; комп'ютерні Telemart/KTC/Brain/Vencon чайники не возять). Rozetka на піддомені
-- bt.rozetka.com.ua. Бекфілу нема — новий збір. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Електрочайники', 'elektrochaynyky')
ON CONFLICT (slug) DO NOTHING;
