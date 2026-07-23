-- 0073: нова категорія АВТОМАГНІТОЛИ (Авто / авто-електроніка).
--
-- Weak-medium матчер — краще за реєстратори (0072), гірше за побутову техніку: бренд+код
-- (GAZER T6009-E90, JVC KD-X282BT, Pioneer MVH) — extract_mpn бере частіше. Заміряно
-- 2026-07-23: Foxtrot MPN 38/42, Allo 34/60, Epicentr 9/60 → 4 спільні ключі (GAZER T6009
-- у Foxtrot+Allo). Per-store історія повна.
--
-- ⚠ GPS-навігатори НЕ додаємо — вмируща категорія (Foxtrot 1 товар, Allo 404, 0 спільних
-- ключів; витіснені смартфонами).
--
-- 5 крамниць (Foxtrot/Epicentr/Allo/Rozetka/Eldorado; Comfy/Moyo окремої категорії не
-- тримають). Rozetka авто — на піддомені auto.rozetka.com.ua. Бекфілу нема. Forward-only,
-- ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Автомагнітоли', 'avtomagnitoly')
ON CONFLICT (slug) DO NOTHING;
