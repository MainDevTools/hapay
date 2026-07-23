-- 0065: нова категорія ЛАНЦЮГОВІ ПИЛИ (бензо/електро/акумуляторні) (Садова техніка).
--
-- ⚠ Слабкий cross-store матчер (як садова/DIY — багатотокенні коди: Husqvarna, Makita,
-- Grunhelm GS5200M) → extract_mpn дробить. Per-store історія повна. Верифіковано
-- 2026-07-23: Allo 60/60.
--
-- Окремо від дискових пил (0054 — електроінструмент). 5 крамниць (Moyo/Eldorado URL не
-- знайдено — пропущено). Rozetka на головному домені (chainsaws). Epicentr — benzopily-i-
-- elektropily. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Ланцюгові пили', 'pyly-lancjugovi')
ON CONFLICT (slug) DO NOTHING;
