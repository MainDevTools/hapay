-- 0174: цільова ціна, стеження за запитом, згода на листи (S29)
--
-- Три речі, яких бракувало, щоб «стежити за ціною» щось означало поза Android:
--
-- 1. ЦІЛЬОВА ЦІНА. Досі ми сповіщали про БУДЬ-ЯКЕ зниження — це шум: людина хоче
--    знати не «подешевшало на 40 грн», а «дійшло до моєї ціни». NULL = стара
--    поведінка (будь-яке зниження), тож наявні записи не міняють сенсу.
--
-- 2. ПАМʼЯТЬ ПРО НАДІСЛАНЕ для стеження ЗА ЗАПИТОМ. У `watchlist` уже є
--    `last_notified_kop`, але вона одна на рядок — для запиту цього мало: під один
--    запит підпадає багато товарів, і про кожен треба памʼятати окремо.
--    ⚠ Наявний `alert_log` НЕ підходить: він ключований на `discount_event_id`
--    (задуманий під алерти по бейджах), а товар може подешевшати БЕЗ активної події
--    знижки — саме такі випадки й ловить фід виміряних знижень (S28).
--
-- 3. ЗГОДА НА ЛИСТИ. Транзакційні листи (підтвердження, скидання) — це відповідь на
--    дію людини; лист «ціна впала» надсилаємо МИ, отже потрібна згода й спосіб
--    відмовитись. За замовчуванням TRUE: людина, яка натиснула «Стежити за ціною»,
--    попросила її сповіщати — але кнопка «не писати» мусить бути завжди.

ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS target_kop BIGINT
  CHECK (target_kop IS NULL OR target_kop > 0);

COMMENT ON COLUMN watchlist.target_kop IS
  'Цільова ціна в копійках (інв. A). NULL = сповіщати про будь-яке зниження.';

ALTER TABLE app_user ADD COLUMN IF NOT EXISTS email_alerts BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN app_user.email_alerts IS
  'Згода на листи про зниження цін. Транзакційних листів (verify/reset) не стосується.';

CREATE TABLE IF NOT EXISTS alert_sent (
  alert_sent_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  watchlist_id     BIGINT NOT NULL REFERENCES watchlist(watchlist_id) ON DELETE CASCADE,
  store_product_id BIGINT NOT NULL REFERENCES store_product(store_product_id),
  price_kop        BIGINT NOT NULL,
  sent_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (watchlist_id, store_product_id)
);

COMMENT ON TABLE alert_sent IS
  'Про що вже сповістили: одна ціна на пару (стеження, товар). Оновлюємо на місці — '
  'наступний лист піде лише якщо ціна впала ЩЕ нижче за ту, про яку вже казали.';

CREATE INDEX IF NOT EXISTS ix_alert_sent_wl ON alert_sent (watchlist_id);
