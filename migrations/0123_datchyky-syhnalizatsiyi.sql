-- 0123: нова категорія ДАТЧИКИ СИГНАЛІЗАЦІЇ (Розумний дім).
--
-- Матчер заміряно 2026-07-24: 0 спільних ключів при живому per-store MPN
-- (Allo 12/60, Epicentr 12/60) — знову парадокс тайлів: Allo Ajax-домінантний
-- (29/60 позицій Ajax), Epicentr — Emos/дешевший тайл. Per-store Omnibus
-- працює. 3 джерела: Allo + Epicentr (парсингом) + Rozetka c235372
-- (пошук-URL). Ajax-фільтровані сторінки (producer=ajax) НЕ реєструємо —
-- беремо чисті категорії, бренд домінує органічно.
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Датчики сигналізації', 'datchyky-syhnalizatsiyi')
ON CONFLICT (slug) DO NOTHING;
