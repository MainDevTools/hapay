-- 0161: досів довідників доставки — друга хвиля (S9, guardrail §7).
--
-- ЛИШЕ виписане з першоджерел (сторінки умов), звірено 2026-07-24. Канал v1:
-- якщо крамниця має власні магазини/точки з БЕЗКОШТОВНИМ самовивозом — він
-- (base=0); інакше — найтиповіший поштовий канал.
--
-- MAUDAU:   НП-відділення від 69 грн, безкоштовно від 2000 (maudau.com.ua/info/delivery;
--           поштомат від 49/2000, кур'єр від 59/2000, Silpo від 45/1199).
-- MakeUp:   НП 69 грн <899, безкоштовно від 899 (makeup.com.ua/ua/delivery/;
--           кур'єр MAKEUP free від 249, Meest 45/від 599, мін. замовлення 249).
-- Yabko:    самовивіз з магазину безкоштовно; НП безкоштовно при передоплаті
--           (jabko.ua/dostavka-i-oplata) → base=0.
-- Eldorado: самовивіз з магазину безкоштовно («протягом години»); НП 159+,
--           Укрпошта 69; безкоштовного порога доставки НЕМА (eldorado.ua/uk/info/delivery/).
-- Zootovary: 59 грн незалежно від ваги, безкоштовно від 500
--           (zootovary.ua/uk/zoomagazin-dostavka-ukrajini-f-10.html).
-- Dnipro-M: самовивіз безкоштовно (600+ точок); НП-відділення 120/від 3000,
--           поштомат 90/від 2000 (dnipro-m.ua/dostavka-i-oplata/) → base=0.
--
-- НЕ виписано (сторінки 403/404 або чисел не публікують) — лишаються
-- no_delivery_data: Foxtrot, Allo, Citrus, Brain, KTC, Telemart (промо-числа
-- ненадійні), Vencon, Storgom, Podorozhnyk, Apteka911, AddUa, MedMagazin,
-- MasterZoo, Antoshka (119 грн лише з hotline-переказу — не першоджерело),
-- Fotosale, Interatletika, Autopresent. Досів — тим самим циклом пізніше.

INSERT INTO delivery_rule (source_id, free_from_kop, base_delivery_kop, np, courier, note)
SELECT s.source_id, v.free_from_kop, v.base_kop, v.np, v.courier, v.note
FROM (VALUES
  ('MAUDAU',    200000::bigint, 6900::bigint, true, true,
   'НП-відділення від 69, free від 2000; поштомат від 49/2000, кур''єр від 59/2000; maudau.com.ua/info/delivery, звірено 2026-07-24'),
  ('MakeUp',    89900::bigint,  6900::bigint, true, true,
   'НП 69 <899, free від 899; кур''єр MAKEUP free від 249, Meest 45/від 599; makeup.com.ua/ua/delivery/, звірено 2026-07-24'),
  ('Yabko',     NULL::bigint,   0::bigint,    true, false,
   'самовивіз безкоштовно; НП безкоштовно при передоплаті; jabko.ua/dostavka-i-oplata, звірено 2026-07-24'),
  ('Eldorado',  NULL::bigint,   0::bigint,    true, true,
   'самовивіз з магазину безкоштовно; НП 159+, Укрпошта 69, free-порога нема; eldorado.ua/uk/info/delivery/, звірено 2026-07-24'),
  ('Zootovary', 50000::bigint,  5900::bigint, true, false,
   '59 грн незалежно від ваги, free від 500; zootovary.ua/.../f-10.html, звірено 2026-07-24'),
  ('DniproM',   NULL::bigint,   0::bigint,    true, true,
   'самовивіз безкоштовно (600+ точок); НП 120/від 3000, поштомат 90/від 2000; dnipro-m.ua/dostavka-i-oplata/, звірено 2026-07-24')
) AS v(name, free_from_kop, base_kop, np, courier, note)
JOIN source s ON s.name = v.name
ON CONFLICT (source_id) DO UPDATE
SET free_from_kop = EXCLUDED.free_from_kop, base_delivery_kop = EXCLUDED.base_delivery_kop,
    np = EXCLUDED.np, courier = EXCLUDED.courier, note = EXCLUDED.note, updated_at = now();

INSERT INTO store_network (source_id, has_pickup, cities_note)
SELECT s.source_id, true, v.note
FROM (VALUES
  ('Yabko',    'магазини Yabko (я́блуко-мережа), самовивіз безкоштовний; jabko.ua, звірено 2026-07-24'),
  ('Eldorado', 'магазини Eldorado, самовивіз «протягом години»; eldorado.ua/uk/info/pickup/, звірено 2026-07-24'),
  ('DniproM',  '600+ точок видачі Dnipro-M; dnipro-m.ua/dostavka-i-oplata/, звірено 2026-07-24'),
  ('Brain',    '45 магазинів у 23 областях; brain.com.ua (шапка/про нас), звірено 2026-07-24'),
  ('Telemart', 'шоуруми: Київ, Дніпро, Харків, Львів, Одеса та ін.; telemart.ua (шапка), звірено 2026-07-24')
) AS v(name, note)
JOIN source s ON s.name = v.name
ON CONFLICT (source_id) DO UPDATE
SET has_pickup = EXCLUDED.has_pickup, cities_note = EXCLUDED.cities_note, updated_at = now();
