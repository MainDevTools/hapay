-- 0150: нова категорія ВУДИЛИЩА (Риболовля).
--
-- Матчер заміряно 2026-07-24: Epicentr 6/60 (розмірні назви «500 см» — слабко).
-- 2 джерела: Epicentr udilishcha (парсингом; спінінги/фідери/махові разом — як
-- ділить крамниця) + Rozetka rods c85169 (загальна, спін-фільтри не реєструємо).
-- Per-store Omnibus. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Вудилища', 'vudylyshcha')
ON CONFLICT (slug) DO NOTHING;
