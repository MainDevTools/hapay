-- 0116: нова категорія ТЕРМОМЕТРИ (Медтехніка) — завершує старт розділу.
--
-- ⚠ Слабкий: 4 крамниці (Allo, Epicentr termometry-meditsinskie, Comfy, Rozetka apteka
-- termometry-dlya-tela c4627816). Descriptive-назви («Термометр-наклейка дитячий Звірі»,
-- «Babyono безконтактний»), дешеві/нішеві бренди (Sensitec, Longevita, Paramed, AICARE) над
-- преміум (Omron, Microlife, Braun) → extract_mpn Allo 3/60, Epicentr 5/60 → 1 спільний ключ.
-- Per-store Omnibus-детекція повна.
--
-- Найкраще покрита категорія медтехніка-старту (4 крамниці). Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Термометри', 'termometry')
ON CONFLICT (slug) DO NOTHING;
