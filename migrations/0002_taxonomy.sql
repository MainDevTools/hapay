-- 0002_taxonomy.sql — сід канонічної зоо-таксономії (§2.6). Ідемпотентно (ON CONFLICT slug).
-- Товари категоризуються за URL у collect (taxonomy.categorize). 'uncategorized' лишається фолбеком.

INSERT INTO category (name, slug) VALUES
 ('Коти · Сухий корм',              'koty-suhyi-korm'),
 ('Пси · Сухий корм',               'psy-suhyi-korm'),
 ('Коти · Консерви',                'koty-konservy'),
 ('Пси · Консерви',                 'psy-konservy'),
 ('Коти · Шампуні та догляд',       'koty-shampuni'),
 ('Пси · Шампуні та догляд',        'psy-shampuni'),
 ('Амуніція (нашийники, повідці)',  'amunitsiya'),
 ('Інше',                           'inshe')
ON CONFLICT (slug) DO NOTHING;
