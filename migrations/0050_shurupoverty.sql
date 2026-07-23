-- 0050: нова категорія ШУРУПОВЕРТИ — старт вертикалі «Інструменти / DIY» (новий розділ
-- «Інструменти»).
--
-- ⚠ СЛАБКИЙ cross-store матчер (на відміну від побутової техніки/догляду). Причина —
-- НЕ дані, а матчер: моделі електроінструменту багатотокенні пробіл-розділені (BOSCH
-- GSR 18 V-50, Metabo PowerMaxx BS, Einhell TE-CD 18/40), а extract_mpn заточений під
-- дужкові appliance-MPN → дробить або віддає None. Заміряно 2026-07-23: спільних
-- extract_mpn-ключів Foxtrot↔Epicentr = 1, хоча спільних модель-токенів = 7. Плюс різний
-- бренд-мікс (Foxtrot — FORTE/STURMAX/СТАЛЬ, Epicentr — Bosch/Metabo/DeWalt/Einhell).
--
-- Отже: per-store історія цін ПОВНА (ядро продукту), cross-store груп мало. Модель-коди
-- реально перетинаються → майбутній тюнінг extract_mpn під tool-моделі (людське рев'ю,
-- інваріант C) підняв би це суттєво. extract_mpn НЕ чіпаємо мовчки.
--
-- 7 крамниць (Foxtrot/Moyo/Allo/Epicentr/Comfy/Rozetka/Eldorado). Rozetka інструмент — на
-- ГОЛОВНОМУ домені rozetka.com.ua (не bt), host-політика пропускає. Бекфілу нема.
-- Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Шуруповерти', 'shurupoverty')
ON CONFLICT (slug) DO NOTHING;
