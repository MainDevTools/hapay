-- 0020: виділити ПРАЛЬНІ МАШИНИ з «побутової техніки» у власну полицю.
--
-- Крок 2 покрокового додавання категорій (після холодильників 0019). Замір 2026-07-22:
-- 497 пральних у 8 крамницях лежали в generic `pobut-tehnika`. Товари вже зібрані —
-- перекатегоризація за назвою, не новий збір.
--
-- Патерн `%пральн%`/`%стиральн%` — у синхроні з `_APPLIANCE_RE`. «пральн» ловить і
-- пральносушильні (комбо перу+сушки) — свідомо, вони теж перуть. Джерело — лише
-- pobut-tehnika. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Пральні машини', 'pralni-mashyny')
ON CONFLICT (slug) DO NOTHING;

UPDATE store_product sp
SET category_id = (SELECT category_id FROM category WHERE slug = 'pralni-mashyny')
WHERE sp.category_id = (SELECT category_id FROM category WHERE slug = 'pobut-tehnika')
  AND (sp.title ILIKE '%пральн%' OR sp.title ILIKE '%стиральн%');
