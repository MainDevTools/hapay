-- 0117: нова категорія ОБ'ЄКТИВИ (Фото-відео) — розгортання Fotosale ушир.
--
-- Преміум-категорія (Canon RF/Sony FE/ZEISS), ціни від тисяч грн — ідеальний
-- профіль для Omnibus-перевірки знижок. Матчер: коди в дужках («(7427C005)»)
-- extract_mpn поки не бере (той самий Canon-патерн, що фотоапарати) → 0/20;
-- per-store історія повна. Джерело: Fotosale /ua/lenses (hub, 20 карток).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Обʼєктиви', 'obyektyvy')
ON CONFLICT (slug) DO NOTHING;
