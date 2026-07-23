-- 0114: нова категорія НЕБУЛАЙЗЕРИ / ІНГАЛЯТОРИ (Медтехніка).
--
-- ⚠ Слабкий + тонкий: 2 крамниці (Rozetka bt-піддомен c2776042 + Epicentr). Descriptive-назви
-- («Інгалятор для носа Poy-Sian», «Mesh Nebulizer SY308»), нішеві/no-name бренди (Ulaizer,
-- Little Doctor, Gamma, Dr.Isla) → extract_mpn Epicentr 8/60. Allo окремої категорії не має
-- (пропуск). Per-store Omnibus-детекція повна.
--
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Небулайзери', 'nebulayzery')
ON CONFLICT (slug) DO NOTHING;
