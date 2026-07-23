-- 0047: нова категорія ЕПІЛЯТОРИ (персональний догляд, розділ «Краса і догляд»).
--
-- Добрий матчер: ті самі моделі Philips Lumea/Braun Silk-epil/Panasonic між крамницями
-- (PHILIPS BRE225/00, BRAUN SES 5/500) → extract_mpn 33-58%, 17 ключів у 2+ крамницях
-- (заміряно 2026-07-23).
--
-- 7 appliance-крамниць (Foxtrot/Moyo/Allo/Epicentr/Comfy/Rozetka/Eldorado). Rozetka на
-- bt-піддомені (жіночі епілятори+бритви). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Епілятори', 'epilyatory')
ON CONFLICT (slug) DO NOTHING;
