-- 0063: нова категорія МОТОКОСИ ТА ТРИМЕРИ ДЛЯ ТРАВИ — старт розділу «Садова техніка».
--
-- ⚠ САДОВІ мотокоси/тримери для трави (бензо/електро/акумуляторні коси), НЕ персональні
-- тримери для бороди (окрема категорія 0046 trymery в «Краса і догляд»). URL крамниць
-- чітко розділяють: Foxtrot trimeri (садові) vs trimery_trymmer (персональні); Rozetka
-- trimmers/c155089 (садові) vs bt trimeri/c4660433 (персональні).
--
-- ⚠ Слабкий cross-store матчер (як DIY-вертикаль, багатотокенні tool-коди: FORTE ЕМК-1600,
-- Bosch EasyGrassCut) → extract_mpn дробить. Per-store історія повна. Верифіковано
-- 2026-07-23: Foxtrot 40/42, Epicentr 59/60, Allo 54/60, Moyo 22/24.
--
-- 6 крамниць (Eldorado садової категорії не знайдено — пропущено). Rozetka на головному
-- домені. Moyo під sadovaya_technika. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Мотокоси та тримери для трави', 'motokosy')
ON CONFLICT (slug) DO NOTHING;
