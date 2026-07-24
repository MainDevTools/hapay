-- 0164: store_network для Stylus — прогалина 0163, впіймана смоком на живій групі
-- (LG 43QNED80A6A: Stylus дешевший на 1555 грн, але програвав без pickup-бонуса).
-- Першоджерело: stls.store/uk/delivery.html, звірено 2026-07-24 — «Самовивіз — це
-- швидкий і зручний спосіб отримати своє замовлення без додаткових витрат»,
-- пункти видачі: Київ (просп. Миколи Бажана, 30), Львів (вул. Бойківська, 1);
-- мінімальна сума замовлення 500 грн.

INSERT INTO store_network (source_id, has_pickup, cities_note)
SELECT s.source_id, true,
       'пункти видачі: Київ (просп. Бажана, 30), Львів (вул. Бойківська, 1); самовивіз безкоштовний, мін. замовлення 500 грн; stls.store/uk/delivery.html, звірено 2026-07-24'
FROM source s WHERE s.name = 'Stylus'
ON CONFLICT (source_id) DO UPDATE
SET has_pickup = EXCLUDED.has_pickup, cities_note = EXCLUDED.cities_note, updated_at = now();
