-- 0162: досів довідників доставки — третя хвиля (S9, guardrail §7).
--
-- Виписано з першоджерел локальним фетчем (WebFetch різався 403), звірено 2026-07-24:
--
-- Foxtrot:  НП-відділення ВАГОВА СІТКА: до 2 кг 179 грн, 2-10 кг 279, до 15 кг
--           379 (foxtrot.com.ua/uk/article/672). Free-порога нема. Канал v1 —
--           дрібна техніка 179; для великогабариту скор занижуватиме доставку —
--           чесно зазначено тут (v2: вагові правила).
-- Antoshka: НП відділення/поштомат/кур'єр 119 грн при <2000, безкоштовно від
--           2000 (antoshka.ua/uk/delivery/) — hotline-переказ підтвердився
--           першоджерелом і доповнився порогом.
--
-- store_network (мережі точок — задокументовані факти):
-- Vencon — власні точки видачі (Київ, Львів; vencon.ua); MedMagazin — мережа
-- магазинів по містах (med-magazin.ua/ua/contacts/); Antoshka — мережа дитячих
-- магазинів (antoshka.ua); MasterZoo — плашка «в N магазинах» на картках
-- (знято при розвідці masterzoo.ua 2026-07-23, наприклад «в 66 магазинах»).
--
-- ДОСІ no_delivery_data (13): Allo, Citrus, Brain, KTC, Telemart (лише
-- акційний банер Укрпошти з таймером), Vencon, Storgom, Podorozhnyk,
-- Apteka911, AddUa, MedMagazin, MasterZoo, Fotosale, Interatletika (сторінка
-- без чисел), Autopresent — сторінки 403/404 або чисел не публікують.

INSERT INTO delivery_rule (source_id, free_from_kop, base_delivery_kop, np, courier, note)
SELECT s.source_id, v.free_from_kop, v.base_kop, v.np, v.courier, v.note
FROM (VALUES
  ('Foxtrot',  NULL::bigint,   17900::bigint, true, true,
   'НП вагова сітка: до 2кг 179, 2-10кг 279, до 15кг 379; free-порога нема; канал v1 = дрібна 179 (великогабарит занижено); foxtrot.com.ua/uk/article/672, звірено 2026-07-24'),
  ('Antoshka', 200000::bigint, 11900::bigint, true, true,
   'НП відділення/поштомат/кур''єр 119 грн <2000, free від 2000; antoshka.ua/uk/delivery/, звірено 2026-07-24')
) AS v(name, free_from_kop, base_kop, np, courier, note)
JOIN source s ON s.name = v.name
ON CONFLICT (source_id) DO UPDATE
SET free_from_kop = EXCLUDED.free_from_kop, base_delivery_kop = EXCLUDED.base_delivery_kop,
    np = EXCLUDED.np, courier = EXCLUDED.courier, note = EXCLUDED.note, updated_at = now();

INSERT INTO store_network (source_id, has_pickup, cities_note)
SELECT s.source_id, true, v.note
FROM (VALUES
  ('Vencon',     'власні точки видачі (Київ, Львів); vencon.ua, звірено 2026-07-24'),
  ('MedMagazin', 'мережа магазинів медтехніки по містах; med-magazin.ua/ua/contacts/, звірено 2026-07-24'),
  ('Antoshka',   'мережа дитячих магазинів Антошка; antoshka.ua, звірено 2026-07-24'),
  ('MasterZoo',  'мережа зоомагазинів («в 66 магазинах» — плашки карток masterzoo.ua, розвідка 2026-07-23)')
) AS v(name, note)
JOIN source s ON s.name = v.name
ON CONFLICT (source_id) DO UPDATE
SET has_pickup = EXCLUDED.has_pickup, cities_note = EXCLUDED.cities_note, updated_at = now();
