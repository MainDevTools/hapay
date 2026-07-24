-- 0166: kind='card' у CHECK черги (S12).
--
-- 0005 закарбував CHECK (kind IN ('hub','page')), 0018 додав 'sitemap'; 0165 завів
-- card-задачі, але констрейнт лишився старим — перший же живий сів упав на
-- CheckViolation (впіймано 2026-07-24 одразу після деплою). Той самий патерн, що 0018.

ALTER TABLE collect_task DROP CONSTRAINT collect_task_kind_check;
ALTER TABLE collect_task ADD CONSTRAINT collect_task_kind_check
  CHECK (kind IN ('hub', 'page', 'sitemap', 'card'));
