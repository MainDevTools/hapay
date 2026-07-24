-- 0160: сів довідників доставки/самовивозу — велика шістка (S9, guardrail §7).
--
-- ЛИШЕ виписане з першоджерел (сторінки умов крамниць), звірено 2026-07-24.
-- Модель v1 спрощена до ОДНОГО «рідного» каналу на крамницю (найдешевший
-- самовивізний/типовий) — повна розкладка в note.
--
-- Rozetka:  точки видачі Rozetka — 49 грн при кошику <1000 грн, безкоштовно
--           від 1000 (help.rozetka.com.ua/p/36).
-- Moyo:     відділення НП — 149 грн, безкоштовно від 4500 грн; поштомат
--           79-139/від 2500; кур'єр 179/від 4500; самовивіз з магазину
--           безкоштовний (moyo.ua/ua/consumers.html). Канал v1 — НП-відділення.
-- Epicentr: центр видачі онлайн-замовлень і поштомати Епіцентра — безкоштовно
--           (epicentrk.ua/ua/faq/onlayn-zamovlennya/..., /info/parcel-locker/).
-- Comfy:    до магазинів Comfy — безкоштовно; перевізники «за тарифами»
--           (faq.comfy.ua/delivery-cost). Канал v1 — магазин.
-- Foxtrot:  чисел НЕ публікує («за тарифами перевізників», faq.foxtrot 404508)
--           → БЕЗ запису (no_delivery_data). Allo: чисел не знайдено → БЕЗ запису.
--
-- Довідник ПЕРЕЗАПИСУВАНИЙ (це не історія цін): ON CONFLICT DO UPDATE.

INSERT INTO delivery_rule (source_id, free_from_kop, base_delivery_kop, np, courier, note)
SELECT s.source_id, v.free_from_kop, v.base_kop, v.np, v.courier, v.note
FROM (VALUES
  ('Rozetka',  100000::bigint, 4900::bigint, true,  true,
   'точки видачі Rozetka: 49 грн <1000, free від 1000; help.rozetka.com.ua/p/36, звірено 2026-07-24'),
  ('Moyo',     450000::bigint, 14900::bigint, true, true,
   'НП-відділення: 149 грн, free від 4500; поштомат 79-139/від 2500, кур''єр 179/від 4500, самовивіз 0; moyo.ua/ua/consumers.html, звірено 2026-07-24'),
  ('Epicentr', NULL::bigint,   0::bigint,    true,  true,
   'центр видачі/поштомат Епіцентра — безкоштовно; epicentrk.ua/ua/faq + /info/parcel-locker/, звірено 2026-07-24'),
  ('Comfy',    NULL::bigint,   0::bigint,    true,  true,
   'до магазинів Comfy — безкоштовно; перевізники за тарифами; faq.comfy.ua/delivery-cost, звірено 2026-07-24')
) AS v(name, free_from_kop, base_kop, np, courier, note)
JOIN source s ON s.name = v.name
ON CONFLICT (source_id) DO UPDATE
SET free_from_kop = EXCLUDED.free_from_kop, base_delivery_kop = EXCLUDED.base_delivery_kop,
    np = EXCLUDED.np, courier = EXCLUDED.courier, note = EXCLUDED.note, updated_at = now();

INSERT INTO store_network (source_id, has_pickup, cities_note)
SELECT s.source_id, true, v.note
FROM (VALUES
  ('Rozetka',  'точки видачі Rozetka по містах (help.rozetka.com.ua/p/36), звірено 2026-07-24'),
  ('Moyo',     'самовивіз з магазину Moyo, готовність ~20 хв (consumers.html), звірено 2026-07-24'),
  ('Epicentr', 'центри видачі в ТЦ Епіцентр (faq), звірено 2026-07-24'),
  ('Comfy',    'магазини Comfy, доставка в магазин безкоштовна (faq.comfy.ua), звірено 2026-07-24')
) AS v(name, note)
JOIN source s ON s.name = v.name
ON CONFLICT (source_id) DO UPDATE
SET has_pickup = EXCLUDED.has_pickup, cities_note = EXCLUDED.cities_note, updated_at = now();
