-- 0005: черга-оренда розподіленого збору (T16 — «усе через телефон, розумний розподіл»).
-- Задача = сторінка, яку збираємо ПОВТОРНО. Телефони НЕ отримують роботу від сервера —
-- вони її ЗАБИРАЮТЬ (pull): оренда з протуханням; смерть телефона посеред задачі
-- повертає її в чергу сама собою.
--
-- Два незалежні регулятори (рішення оператора 2026-07-19):
--   * розліт по крамниці: оренда будь-якої задачі source зсуває not_before УСІХ його
--     задач на +15 хв → два телефони фізично не вдарять по одній крамниці поспіль;
--     по РІЗНИХ крамницях — паралельно скільки завгодно;
--   * свіжість сторінки: repeat_min (дефолт 720 = 2×/добу, каденс §10).

CREATE TABLE collect_task (
  task_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source      TEXT NOT NULL,                 -- ключ HTML_SOURCES (сервер — авторитет)
  url         TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'page' CHECK (kind IN ('hub','page')),
  priority    INT  NOT NULL DEFAULT 100,     -- менше = раніше в межах source
  repeat_min  INT  NOT NULL DEFAULT 720,     -- за скільки хв перезбирати ЦЮ сторінку
  not_before  TIMESTAMPTZ NOT NULL DEFAULT now(),
  leased_by   TEXT,                          -- хто орендує (acct:<id> / label токена)
  leased_until TIMESTAMPTZ,                  -- протухання оренди → задача знову вільна
  last_done_at TIMESTAMPTZ,
  last_status TEXT,                          -- 'ok' | 'fail:<чому>'
  fail_count  INT NOT NULL DEFAULT 0,        -- поспіль; скидається на успіху
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, url)
);

CREATE INDEX ix_ct_ready ON collect_task (not_before);
