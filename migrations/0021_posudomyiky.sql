-- 0021: виділити ПОСУДОМИЙКИ з «побутової техніки» у власну полицю.
--
-- Крок 3 покрокового додавання категорій (після холодильників 0019, пральних 0020).
-- Замір 2026-07-22: 290 посудомийок у 5 крамницях у generic `pobut-tehnika`. Товари
-- вже зібрані — перекатегоризація за назвою. Останнє велике з бакета: далі лишається
-- дрібне (мультиварки/праски/дрібна кухня), яке розщепимо за потреби.
--
-- Патерн `%посудомий%`/`%посудомоеч%` — у синхроні з `_APPLIANCE_RE`. Джерело — лише
-- pobut-tehnika. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Посудомийні машини', 'posudomyiky')
ON CONFLICT (slug) DO NOTHING;

UPDATE store_product sp
SET category_id = (SELECT category_id FROM category WHERE slug = 'posudomyiky')
WHERE sp.category_id = (SELECT category_id FROM category WHERE slug = 'pobut-tehnika')
  AND (sp.title ILIKE '%посудомий%' OR sp.title ILIKE '%посудомоеч%');
