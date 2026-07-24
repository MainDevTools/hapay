-- 0156: нова категорія ЗАСОБИ ДЛЯ ПОСУДУ (Побутова хімія).
--
-- Заміряно 2026-07-24: MAUDAU zasoby-dlia-myttia-posudu (48 поз., релевантних
-- 47 — Fairy-домінанта). ⚠ ЄДИНЕ джерело. Варіантність обсягів (450/900 мл) —
-- слабкий крос за визначенням; per-store Omnibus.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Засоби для посуду', 'zasoby-dlya-posudu')
ON CONFLICT (slug) DO NOTHING;
