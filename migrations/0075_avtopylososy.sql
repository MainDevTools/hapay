-- 0075: нова категорія АВТОПИЛОСОСИ (Авто) — 12V/акумуляторні пилососи для салону.
--
-- ⚠ Слабкий cross-store матчер (бренд+код часто описовий: Voin V-8, Baseus, Karcher CVH) →
-- extract_mpn дробить/None. Per-store історія повна. Верифіковано 2026-07-23: Foxtrot 41/42,
-- Epicentr 55/60, Allo 56/60.
--
-- Окремо від побутових пилососів (pylososy). 5 крамниць (Eldorado лише фасет bagless →
-- пропущено). Rozetka авто на піддомені. Comfy — фасет hand-vacuum-cleaners (авто).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Автопилососи', 'avtopylososy')
ON CONFLICT (slug) DO NOTHING;
