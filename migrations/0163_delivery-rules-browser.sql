-- 0163: досів довідників — браузерна хвиля (S9, guardrail §7). Звірено 2026-07-24
-- у браузер-панелі (сторінки, що різали 403 і WebFetch, і локальний urllib).
--
-- Канал v1 = безкоштовний самовивіз/власна доставка (усі 8 — процитовано зі
-- сторінок умов; поштові цифри — в note):
-- Telemart:   «Видача товарів самовивозом в нашому магазині безкоштовна».
-- MasterZoo:  самовивіз з магазину безкоштовно; НП-відділення/поштомат 49 грн /
--             free від 850; кур'єр НП 99/від 1500; власна 149/від 799.
-- Vencon:     самовивіз Київ/Львів (заголовок стор. умов); тарифи перевізників
--             без публічних чисел.
-- Storgom:    видача товару з пункту (09:00-19:30); Київ-кур'єр free від 7000,
--             область 349.
-- KTC:        «Безкоштовно доставляємо… в обраний магазин КТС або точку
--             Київстар»; НП free від 5000 (ВИНЯТКИ: зарядні станції, генератори,
--             ДБЖ, принтери, крісла тощо — платно); поштомат free від 999.
-- Citrus:     «Доставка… до найближчого магазину "Цитрус" здійснюється безкоштовно».
-- Podorozhnyk: отримання в аптеці мережі (~140 аптек — плашки «в 138 аптеках»).
-- Stylus:     власна доставка «до парадного» безкоштовна (тарифікується лише
--             занесення поверхами); кур'єрська від 249, мін. замовлення 3000.
--
-- БЕЗ правил лишаються 8 — з ПРИЧИНАМИ:
-- Allo — маркетплейс: «спільні правила для всіх продавців» = єдиного правила
--   НЕ ІСНУЄ принципово (постійний no_delivery_data, не «не дістали»);
-- Autopresent — «безкоштовно від 1000 грн» підтверджено, але базовий тариф
--   <1000 не публікується числом → половинчасте правило не сіємо;
-- Brain, Interatletika — сторінки без чисел; Fotosale — уривчасто (кур'єр 300,
--   преміум free від 20000 — не базовий канал); MedMagazin, Apteka911, AddUa —
--   сторінки умов не знайдено/без чисел.

INSERT INTO delivery_rule (source_id, free_from_kop, base_delivery_kop, np, courier, note)
SELECT s.source_id, NULL::bigint, 0::bigint, v.np, v.courier, v.note
FROM (VALUES
  ('Telemart',    true,  false, 'самовивіз із шоурумів безкоштовний; telemart.ua/ua/content/payment-and-delivery.html, звірено 2026-07-24'),
  ('MasterZoo',   true,  true,  'самовивіз з магазину безкоштовно; НП 49/від 850, кур''єр 99/від 1500, власна 149/від 799; masterzoo.ua/ua/oplata-i-dostavka/, звірено 2026-07-24'),
  ('Vencon',      true,  true,  'самовивіз Київ/Львів; тарифи перевізників без публічних чисел; vencon.ua/ua/oplata-i-dostavka, звірено 2026-07-24'),
  ('Storgom',     true,  true,  'видача з пункту безкоштовна; Київ-кур''єр free від 7000, область 349; storgom.ua/ua/oplata.html, звірено 2026-07-24'),
  ('KTC',         true,  false, 'самовивіз у магазин КТС/точку Київстар безкоштовно; НП free від 5000 (винятки: станції/генератори/ДБЖ/принтери/крісла), поштомат free від 999; ktc.ua/about/shipping.html, звірено 2026-07-24'),
  ('Citrus',      true,  true,  'доставка до магазину Цитрус безкоштовна; citrus.ua/dostavka/, звірено 2026-07-24'),
  ('Podorozhnyk', false, false, 'отримання в аптеці мережі (~140 аптек); podorozhnyk.ua (плашки наявності), звірено 2026-07-24'),
  ('Stylus',      true,  true,  'власна доставка до парадного безкоштовна (платне лише занесення); кур''єрська від 249, мін. 3000; stls.store/uk/delivery.html, звірено 2026-07-24')
) AS v(name, np, courier, note)
JOIN source s ON s.name = v.name
ON CONFLICT (source_id) DO UPDATE
SET free_from_kop = EXCLUDED.free_from_kop, base_delivery_kop = EXCLUDED.base_delivery_kop,
    np = EXCLUDED.np, courier = EXCLUDED.courier, note = EXCLUDED.note, updated_at = now();

INSERT INTO store_network (source_id, has_pickup, cities_note)
SELECT s.source_id, true, v.note
FROM (VALUES
  ('KTC',         'магазини КТС + точки Київстар; ktc.ua/about/shipping.html, звірено 2026-07-24'),
  ('Citrus',      'магазини Цитрус (доставка в магазин безкоштовна); citrus.ua/dostavka/, звірено 2026-07-24'),
  ('Storgom',     'пункт видачі Storgom (09:00-19:30); storgom.ua/ua/oplata.html, звірено 2026-07-24'),
  ('Podorozhnyk', 'мережа аптек ~140 точок (плашки «в 138 аптеках»); podorozhnyk.ua, звірено 2026-07-24'),
  ('Fotosale',    'магазини: Київ, Львів, Харків, Одеса, Дніпро (шапка сайту); fotosale.ua, звірено 2026-07-24')
) AS v(name, note)
JOIN source s ON s.name = v.name
ON CONFLICT (source_id) DO UPDATE
SET has_pickup = EXCLUDED.has_pickup, cities_note = EXCLUDED.cities_note, updated_at = now();
