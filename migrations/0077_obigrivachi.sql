-- 0077: нова категорія ОБІГРІВАЧІ — старт розділу «Клімат» (кліматична техніка).
-- (Кондиціонери kondycionery перенесено сюди з «Побутова техніка» — лише зміна розділу в
--  taxonomy CATEGORY_UI, без міграції даних.)
--
-- ⚠ Слабко-середній матчер: багато house-брендів без коду (UP!, HausMark, Domotec, Termia),
-- лише преміум має чистий SKU (Zanussi ZOH/CS-09, Electrolux). extract_mpn Epicentr 13/60.
-- Per-store історія повна.
--
-- ⚠ Широка «Обігрівачі» лише де крамниця має реальну broad-категорію (Epicentr obogrevateli,
-- Rozetka bt heaters c80192, Comfy heater, Eldorado node c1039065). Foxtrot/Allo/Moyo дроблять
-- за типом без робочого broad-лістинга (Foxtrot 7 масляних, Allo 0, Moyo 1 — лендінги) →
-- пропущено; їх типи можна додати окремими категоріями пізніше. 4 крамниці. Rozetka на
-- bt-піддомені. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Обігрівачі', 'obigrivachi')
ON CONFLICT (slug) DO NOTHING;
