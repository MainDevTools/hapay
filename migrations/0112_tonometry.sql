-- 0112: нова категорія ТОНОМЕТРИ — старт розділу «Медтехніка» (прилади для здоров'я).
--
-- ⚠ Weak-medium матчер (слабше за прогноз): преміум збігається (Omron, Microlife BP B3
-- AFIB, A&D UA-651), АЛЕ дешеві бренди (Gamma, Longevita, Oromed) розмивають + короткі
-- моделі-коди (BP B3, M2, UA-651) extract_mpn бере непослідовно. Заміряно 2026-07-23:
-- extract_mpn Allo 9/60, Epicentr 21/60 → лише 2 спільні ключі у 2+. Per-store історія повна.
--
-- 4 крамниці (Foxtrot/Eldorado не знайдено). Rozetka на bt-піддомені (tonometry). Comfy
-- tonometers. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Тонометри', 'tonometry')
ON CONFLICT (slug) DO NOTHING;
