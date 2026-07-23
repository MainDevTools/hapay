-- 0090: нова категорія ЕКШН-КАМЕРИ — старт розділу «Фото-відео».
-- (Наявну «Фото»=камери перенесено сюди з «Електроніка» — лише зміна розділу в taxonomy.)
--
-- ⚠ Weak-medium матчер: преміум концентрований (GoPro HERO13, DJI Osmo Action, Insta360),
-- АЛЕ регіональні part-numbers різняться між крамницями (GoPro CHDHX-… vs CHDHW-…) +
-- домішуються дешеві (SJCAM, Hoco, ThiEye) → extract_mpn Foxtrot 18/42, Allo 20/60, лише
-- 4 спільні ключі у 2+ (заміряно 2026-07-23). Per-store історія повна.
--
-- 6 крамниць. Rozetka на головному домені. Epicentr — videokamery-i-ekshn-kamery (з відео-
-- камерами). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Екшн-камери', 'ekshn-kamery')
ON CONFLICT (slug) DO NOTHING;
