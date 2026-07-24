-- 0142: нова категорія РАДІАТОРИ ОПАЛЕННЯ (Опалення).
--
-- Матчер заміряно 2026-07-24: 0 спільних (Epicentr 4/60 Polux-тайл + Vencon
-- 4/27; розмірні назви «500/96» матчер бере погано). 2 джерела: Epicentr
-- radiatory-otopleniya (загальна) + Vencon stalnye-radiatory (підтип —
-- загальна radiatory-otopleniya у Vencon віддає хаб виробників, 0 карток).
-- Per-store Omnibus повний. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Радіатори опалення', 'radiatory-opalennya')
ON CONFLICT (slug) DO NOTHING;
