-- 0121: нова категорія IP-КАМЕРИ — старт розділу «Розумний дім / безпека».
--
-- Матчер заміряно 2026-07-24: ПАРАДОКС — високий per-store MPN (Allo 37/60,
-- Foxtrot 23/42, Epicentr 21/60), але 0 спільних ключів: крамниці тримають
-- РІЗНИЙ тайл брендів (Allo — Xiaomi/Imou, Epicentr — TP-Link Tapo, Foxtrot —
-- Dahua) — класична pro-варіативність. Крос слабкий; per-store Omnibus сильний
-- (моделі з кодами, преміум-ціни). 4 джерела: Allo/Epicentr/Foxtrot (парсингом)
-- + Rozetka c156790 (пошук-URL). Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('IP-камери', 'ip-kamery')
ON CONFLICT (slug) DO NOTHING;
