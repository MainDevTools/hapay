-- 0171: аудит мусить пережити видалення акаунта (S16).
--
-- Право на забуття вимагає ВИДАЛИТИ акаунт; слід адмін-дій вимагає ЗБЕРЕГТИ, хто що
-- кому зробив. FK з 0170 роблять це неможливим: actor_id NOT NULL без каскаду взагалі
-- блокує DELETE app_user.
--
-- Розв'язка: денормалізувати email у сам запис (знімок на момент дії) і послабити FK.
-- Так рядок лишається читабельним — «admin@x знизив роль user@y» — навіть коли жодного
-- з акаунтів уже нема. Особисті дані при цьому не «воскресають»: у журналі лишається
-- рівно те, що адміністратор і так бачив, коли виконував дію.

ALTER TABLE admin_audit ADD COLUMN IF NOT EXISTS actor_email  TEXT;
ALTER TABLE admin_audit ADD COLUMN IF NOT EXISTS target_email TEXT;

-- заднім числом заповнюємо наявні записи (їхні акаунти ще живі)
UPDATE admin_audit a SET actor_email = u.email
  FROM app_user u WHERE u.user_id = a.actor_id AND a.actor_email IS NULL;
UPDATE admin_audit a SET target_email = u.email
  FROM app_user u WHERE u.user_id = a.target_id AND a.target_email IS NULL;

-- FK більше не тримають акаунт «в заручниках» у журналу
ALTER TABLE admin_audit ALTER COLUMN actor_id DROP NOT NULL;
ALTER TABLE admin_audit DROP CONSTRAINT IF EXISTS admin_audit_actor_id_fkey;
ALTER TABLE admin_audit DROP CONSTRAINT IF EXISTS admin_audit_target_id_fkey;
ALTER TABLE admin_audit ADD CONSTRAINT admin_audit_actor_id_fkey
  FOREIGN KEY (actor_id)  REFERENCES app_user(user_id) ON DELETE SET NULL;
ALTER TABLE admin_audit ADD CONSTRAINT admin_audit_target_id_fkey
  FOREIGN KEY (target_id) REFERENCES app_user(user_id) ON DELETE SET NULL;
