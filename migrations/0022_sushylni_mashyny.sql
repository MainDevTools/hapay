-- 0022: виділити СУШИЛЬНІ МАШИНИ з «побутової техніки» у власну полицю.
--
-- Крок 4. Замір 2026-07-22: лишок generic-бакета (303) виявився не «дрібним», а майже
-- цілком сушильними машинами (268 з 303, «сушильна»+«сушильная»). Товари вже зібрані —
-- перекатегоризація за назвою.
--
-- Порядок важливий: пральні (0020) вже забрали «прально-сушильні» комбо (мають «пральн»),
-- тож у pobut-tehnika лишились ЧИСТІ сушильні. Патерн `%сушильн%` — у синхроні з
-- `_APPLIANCE_RE`. «сушарка» (овочі/білизна) свідомо НЕ беремо. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Сушильні машини', 'sushylni-mashyny')
ON CONFLICT (slug) DO NOTHING;

UPDATE store_product sp
SET category_id = (SELECT category_id FROM category WHERE slug = 'sushylni-mashyny')
WHERE sp.category_id = (SELECT category_id FROM category WHERE slug = 'pobut-tehnika')
  AND sp.title ILIKE '%сушильн%';
