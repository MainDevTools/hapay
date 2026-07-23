-- 0052: нова категорія БОЛГАРКИ / КУТОШЛІФУВАЛЬНІ МАШИНИ (КШМ) (Інструменти / DIY).
--
-- ⚠ Слабкий cross-store матчер (як уся DIY-вертикаль, див. 0050): tool-моделі багато-
-- токенні (Bosch GWS, Makita GA9020, СТАЛЬ КШМ 72-12) → extract_mpn дробить. Per-store
-- історія цін повна. Верифіковано 2026-07-23: Foxtrot 42/42, Epicentr 58/60 — болгарки.
--
-- ⚠ Межа болгарки↔шліфмашини: беру angle-grinder-специфічні URL де є (Foxtrot uglovye-
-- bolgarki, Epicentr bolgarki, Moyo bolgarky, Allo bolgarki, Comfy angle-grinders). У
-- Rozetka (sanders c152503) / Eldorado (c1284670) категорія ширша «Шліфмашини» — домінують
-- болгарки, приймаємо (орбітальні шліфмашини — потенційно окрема категорія пізніше).
--
-- 7 крамниць. Rozetka на головному домені. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Болгарки (КШМ)', 'bolharky')
ON CONFLICT (slug) DO NOTHING;
