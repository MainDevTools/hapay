-- 0139: нова категорія 3D-ПРИНТЕРИ (старт розділу «3D-друк»).
--
-- Матчер заміряно 2026-07-24: старт розділу «3D-друк». Allo 12/60 + Epicentr 15/60 + Rozetka c1593467. 3 СПІЛЬНІ ключі (Creality/Bambu) — слабко-середній.
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('3D-принтери', '3d-printery')
ON CONFLICT (slug) DO NOTHING;
