-- 0019: виділити ХОЛОДИЛЬНИКИ з широкого лістинга «побутова техніка» у власну полицю.
--
-- Крок 1 покрокового додавання категорій. Товари вже зібрані (заміряно 2026-07-22:
-- 1194 холодильники в 9 крамницях лежали в generic `pobut-tehnika`) — тут не новий
-- збір, а перекатегоризація за назвою, як 0009 для audio/aksesuary. `taxonomy.refine_
-- category` уточнює на майбутнє (pobut-tehnika + «холодильник» → holodylnyky); ця
-- міграція виправляє вже наявні.
--
-- Патерн `%холодильник%` — у синхроні з `_APPLIANCE_RE` (те саме слово). Спрацьовує
-- лише на назвах приладу цього класу, тож інші прилади бакета не чіпає. Джерело —
-- лише pobut-tehnika (звідти й прийшли). Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Холодильники', 'holodylnyky')
ON CONFLICT (slug) DO NOTHING;

UPDATE store_product sp
SET category_id = (SELECT category_id FROM category WHERE slug = 'holodylnyky')
WHERE sp.category_id = (SELECT category_id FROM category WHERE slug = 'pobut-tehnika')
  AND sp.title ILIKE '%холодильник%';
