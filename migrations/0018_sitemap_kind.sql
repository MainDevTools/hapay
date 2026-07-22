-- 0018: kind='sitemap' у черзі збору (T20, sitemap-відкриття).
--
-- 0005 закарбував CHECK (kind IN ('hub','page')) — і правильно зробив: сервер-авторитет
-- не приймає вигаданих видів задач. Sitemap-відкриття (2026-07-22) додає третій легітимний
-- вид: задача «прочитай sitemap крамниці» (статичний XML для краулерів; lease віддає її
-- телефону ЗАВЖДИ як fetch). Розширюємо перелік — форвардно, без зміни даних.

ALTER TABLE collect_task DROP CONSTRAINT collect_task_kind_check;
ALTER TABLE collect_task ADD CONSTRAINT collect_task_kind_check
  CHECK (kind IN ('hub', 'page', 'sitemap'));
