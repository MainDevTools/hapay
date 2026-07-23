-- 0130: нова категорія ТЕРМОСИ (Туризм).
--
-- Матчер заміряно 2026-07-24: 0 спільних ключів при живому per-store MPN
-- (Allo 24/60 Xiaomi-тайл, Epicentr 13/60 Flamberg-тайл) — знову парадокс
-- тайлів. 3 джерела: Allo + Epicentr (парсингом) + Rozetka c4627638
-- (termosy-i-butylki, пошук-URL). Per-store Omnibus повний. Бекфілу нема.
-- Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Термоси', 'termosy')
ON CONFLICT (slug) DO NOTHING;
