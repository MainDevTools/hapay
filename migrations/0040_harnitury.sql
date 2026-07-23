-- 0040: виділити ГАРНІТУРИ з «audio» (навушники) у власну полицю.
--
-- Розщеплення за назвою, як прилади з pobut-tehnika: audio містить і навушники, і
-- гарнітури (навушники з мікрофоном). Замір 2026-07-23: 329 з 1643 audio-товарів —
-- гарнітури. Виділяємо за словом, яке дала САМА крамниця («Гарнітура …»), тож межа
-- чиста (довіряємо класифікації крамниці). `taxonomy.refine_category` розводить на
-- майбутнє (audio + «гарнітур» → harnitury); ця міграція виправляє наявні.
--
-- Патерн `%гарнітур%`/`%headset%` — у синхроні з `_HEADSET_RE`. Джерело — лише audio.
-- Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Гарнітури', 'harnitury')
ON CONFLICT (slug) DO NOTHING;

UPDATE store_product sp
SET category_id = (SELECT category_id FROM category WHERE slug = 'harnitury')
WHERE sp.category_id = (SELECT category_id FROM category WHERE slug = 'audio')
  AND (sp.title ILIKE '%гарнітур%' OR sp.title ILIKE '%headset%');
