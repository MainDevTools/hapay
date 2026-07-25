-- 0169: верифікація email + скидання пароля (S13). Реєстрація доти видавала JWT без
-- підтвердження, а забутий пароль = втрачений акаунт назавжди.
--
-- account_token: одноразові коди (verify/reset). Зберігаємо ХЕШ коду (sha256), не сам
-- код — витік БД не дає активних токенів (та сама логіка, що пароль ніколи не plaintext).
-- Код у листі — єдине місце plaintext. TTL у expires_at; одноразовість — used_at.

ALTER TABLE app_user ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS account_token (
  token_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
  kind        TEXT NOT NULL CHECK (kind IN ('verify','reset')),
  code_hash   TEXT NOT NULL,                      -- sha256(код), НІКОЛИ не сам код
  expires_at  TIMESTAMPTZ NOT NULL,
  used_at     TIMESTAMPTZ,                        -- NULL = ще не використаний
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- пошук активного токена при consume: за юзером+видом, свіжі першими
CREATE INDEX IF NOT EXISTS ix_account_token_lookup
  ON account_token (user_id, kind, used_at, expires_at);
