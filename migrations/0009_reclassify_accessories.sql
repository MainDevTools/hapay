-- 0009: разова рекласифікація аксесуарів, що просочились у пристроєві категорії.
--
-- Brain-лістинг «Смартфони та зв'язок» (широкий департамент) містить телефони +
-- кабелі + навушники впереміш; тегування всього лістинга як smartfony (0007) + бекфіл
-- (0008) загнали кабелі/навушники в «Смартфони». Тепер `taxonomy.refine_category`
-- уточнює категорію за назвою на майбутнє; ця міграція виправляє вже наявні.
--
-- Патерни — у синхроні з `refine_category` (ті самі слова). Спрацьовують лише на назвах,
-- яких у назві самого пристрою не буває (кабель/навушники…), тож телефони не чіпає.
-- Порядок: спершу audio (навушники), тоді aksesuary (решта). Forward-only, ідемпотентно.

-- навушники / гарнітура → audio
UPDATE store_product sp
SET category_id = (SELECT category_id FROM category WHERE slug = 'audio')
WHERE sp.category_id IN (SELECT category_id FROM category
                         WHERE slug IN ('smartfony', 'noutbuky', 'planshety', 'tv'))
  AND (sp.title ILIKE '%навушник%' OR sp.title ILIKE '%гарнітур%'
       OR sp.title ILIKE '%airpods%' OR sp.title ILIKE '%earbuds%');

-- кабелі / зарядки / чохли / power bank / стилус → aksesuary
UPDATE store_product sp
SET category_id = (SELECT category_id FROM category WHERE slug = 'aksesuary')
WHERE sp.category_id IN (SELECT category_id FROM category
                         WHERE slug IN ('smartfony', 'noutbuky', 'planshety', 'tv'))
  AND (sp.title ILIKE '%кабель%' OR sp.title ILIKE '%power bank%'
       OR sp.title ILIKE '%павербанк%' OR sp.title ILIKE '%повербанк%'
       OR sp.title ILIKE '%зарядний пристрій%' OR sp.title ILIKE '%зовнішній акумулятор%'
       OR sp.title ILIKE '%чохол%' OR sp.title ILIKE '%захисне скло%'
       OR sp.title ILIKE '%захисна плівк%' OR sp.title ILIKE '%автотримач%'
       OR sp.title ILIKE '%стилус%');
