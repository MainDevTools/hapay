-- 0054: нова категорія ДИСКОВІ (ЦИРКУЛЯРНІ) ПИЛИ (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні (Bosch GKS 190, Makita HS7601K) → extract_mpn дробить. Per-store історія цін
-- повна. Верифіковано 2026-07-23: Foxtrot 42/42, Epicentr 58/60, Allo 58/60.
--
-- ⚠ Rozetka (pily-i-plitkorezy) — ширша «Пили і плиткорізи», Foxtrot (saw) домішує торцю-
-- вальні; дискові домінують, приймаємо. 7 крамниць. Rozetka на головному домені.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Дискові пили', 'pyly-dyskovi')
ON CONFLICT (slug) DO NOTHING;
