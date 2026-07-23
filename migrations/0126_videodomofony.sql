-- 0126: нова категорія ВІДЕОДОМОФОНИ (Розумний дім).
--
-- Обрано «відеодомофони», а не «відеодзвінки»: чисті категорії дзвінків-з-відео
-- мають лише фільтрами (Allo vid-videozvonki, Rozetka osobennosti=s-videokameroy)
-- — фільтри не реєструємо. Матчер заміряно 2026-07-24: Allo n=60, MPN 18/60,
-- відео-частка 50/60 (Hikvision/Slinex — коди чіткі). 2 джерела: Allo
-- (парсингом) + Rozetka c259633 (пошук-URL). Epicentr domofony НЕ взято —
-- мішає аудіотрубки/аксесуари (BCOM UKP-12M перша ж позиція).
-- Бекфілу нема. Forward-only, ідемпотентно.

INSERT INTO category (name, slug) VALUES
  ('Відеодомофони', 'videodomofony')
ON CONFLICT (slug) DO NOTHING;
