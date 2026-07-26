-- 0170: адмін-функції під ролями (S15). Ролі (user/collector/moderator/admin) є від
-- S11 — додаємо стан бану й аудит адмін-дій, щоб ролі отримали сенс.
--
-- is_active: бан = false; login відхиляє. admin_audit: незмінний слід кожної адмін-
-- мутації (хто actor, що action, кому target) — привілейовані дії мусять лишати слід.

ALTER TABLE app_user ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS admin_audit (
  audit_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id   BIGINT NOT NULL REFERENCES app_user(user_id),   -- хто зробив
  action     TEXT NOT NULL,                                  -- 'set_role' | 'set_active'
  target_id  BIGINT REFERENCES app_user(user_id),            -- над ким
  detail     TEXT,                                           -- напр. 'user→moderator' / 'active=false'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_admin_audit_created ON admin_audit (created_at DESC);
