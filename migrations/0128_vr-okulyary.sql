-- 0128: нова категорія VR-ОКУЛЯРИ (Геймінг).
--
-- Матчер заміряно 2026-07-24: 1 спільний ключ (Allo 14/60, Epicentr 6/60 —
-- дешевий тайл картонних/телефонних VR розмиває Quest/PS VR; преміум тонкий
-- у лістингу). 3 джерела: Allo + Epicentr (парсингом) + Rozetka c131143
-- (пошук-URL). Per-store Omnibus повний. Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('VR-окуляри', 'vr-okulyary')
ON CONFLICT (slug) DO NOTHING;
