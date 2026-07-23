-- 0067: нова категорія КУЛЬТИВАТОРИ ТА МОТОБЛОКИ (Садова техніка).
--
-- ⚠ Слабкий cross-store матчер (як садова/DIY — багатотокенні коди: Forte МКБ-25 LUX,
-- Konner&Sohnen KS 1000T) → extract_mpn дробить. Per-store історія повна. Верифіковано
-- 2026-07-23: Foxtrot 41/42, Allo 60/60, Moyo 17/20.
--
-- Об'єднана: культиватори + мотоблоки (крамниці тримають однією категорією). 6 крамниць.
-- Rozetka на головному домені (слаг kulivatory — так у крамниці). Moyo під sadovaya_technika,
-- Allo слаг motobloki. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Культиватори та мотоблоки', 'kultyvatory')
ON CONFLICT (slug) DO NOTHING;
