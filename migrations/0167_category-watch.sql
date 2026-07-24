-- 0165: стеження за КАТЕГОРІЄЮ (UX-пакет 2026-07-24). kind='category' у watchlist
-- існував від S11, але не мав ні UI, ні механіки сповіщень. Водяний знак для
-- категорійних новин — час останнього сповіщення (аналог last_notified_kop у
-- товарних, тільки віссю є час появи нових discount_event, не ціна).

ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS last_notified_at TIMESTAMPTZ;
