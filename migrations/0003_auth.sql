-- 0003: публічні акаунти + ролі (S11 auth). Клієнт у базу не пише — лише через валідований API.
-- Пароль — pbkdf2_sha256 (stdlib, api/auth.py); роль керує доступом до write-ендпоінтів.

CREATE TABLE app_user (
  user_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email         TEXT NOT NULL,
  password_hash TEXT NOT NULL,               -- pbkdf2_sha256$iters$salt$hash (НІКОЛИ не plaintext)
  role          TEXT NOT NULL DEFAULT 'user'
                CHECK (role IN ('user','collector','moderator','admin')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);
-- унікальність email БЕЗ огляду на регістр (Foo@x = foo@x)
CREATE UNIQUE INDEX ux_app_user_email ON app_user (lower(email));

-- watchlist тепер може належати app-юзеру; tg_user_id лишаємо для Telegram Mini App (сумісність)
ALTER TABLE watchlist ALTER COLUMN tg_user_id DROP NOT NULL;
ALTER TABLE watchlist ADD COLUMN user_id BIGINT REFERENCES app_user(user_id) ON DELETE CASCADE;
ALTER TABLE watchlist ADD CONSTRAINT wl_owner_present
  CHECK (tg_user_id IS NOT NULL OR user_id IS NOT NULL);   -- у запису має бути хоч один власник
CREATE INDEX ix_wl_app_user ON watchlist (user_id);
