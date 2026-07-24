-- 0168: разова рекласифікація явно НЕ-електроніки, що просочилась у device-категорії
-- з АКЦІЙНИХ лендингів Allo (hub-дефолт category=smartfony застосовується до будь-якого
-- акційного товару). Впіймано візуальним прогоном 2026-07-25: у «Смартфонах» першою
-- висіла «Сковорода RINGEL Koriander глибока 24 см» від Allo. taxonomy.refine_category
-- тепер скидає такі в 'inshe' на майбутнє (правило _NON_DEVICE_RE); ця міграція
-- виправляє вже наявні. Патерни — у СИНХРОНІ з _NON_DEVICE_RE (ті самі слова).
-- Forward-only, ідемпотентно. `посуд%` не чіпає посудомийки — вони не в device-категоріях.

UPDATE store_product sp
SET category_id = (SELECT category_id FROM category WHERE slug = 'inshe')
WHERE sp.category_id IN (SELECT category_id FROM category
                         WHERE slug IN ('smartfony', 'noutbuky', 'planshety', 'tv'))
  AND sp.title ~* ('сковор|каструл|сотейник|казан|друшляк|дуршлаг|посуд|тарілк|салатник|'
                   || 'горнятк|горщик|виделк|скатерт|рушник|штор|гардин|тюль|'
                   || 'подушк|ковдр|простир|наматрац|плед');
