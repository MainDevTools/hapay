-- 0085: нова категорія ЕЛЕКТРОСАМОКАТИ (Спорт / електротранспорт).
--
-- ✓ СИЛЬНИЙ cross-store матчер — концентровані бренди з чистим кодом (Xiaomi Electric
-- Scooter M365, Proove Model Urban/X-City, Segway Ninebot, Kugoo). Заміряно 2026-07-23:
-- extract_mpn Epicentr 16/60, Foxtrot 23/42, Allo 22/60 → 16 спільних ключів у 2+ крамницях.
-- Per-store історія повна. (Найсильніша категорія розділу «Спорт».)
--
-- 6 крамниць (Eldorado — лише фасет широкого «Електротранспорт» з гіробордами → пропущено).
-- Rozetka на головному домені. Foxtrot слаг girobordi_elektrosamokat, Moyo під gadgets/
-- elektro_transport. Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Електросамокати', 'elektrosamokaty')
ON CONFLICT (slug) DO NOTHING;
