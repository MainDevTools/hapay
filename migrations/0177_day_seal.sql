-- 0177: щоденна ПЕЧАТКА спостережень — доказовість замість обіцянки (S31)
--
-- Ми стверджуємо: «історія append-only, нічого не переписуємо заднім числом». Досі це
-- трималось на нашому слові плюс тригері в базі, якого ніхто ззовні не бачить.
-- Технічно нам ніщо не заважало переписати вчорашню ціну — і ніхто б не помітив.
--
-- Печатка: корінь Меркла над УСІМА снапшотами доби + ланцюжок від попередньої доби.
-- Змінити один запис заднім числом → зміниться корінь → зламається весь ланцюжок далі.
--
-- ⚠ ЧОГО ЦЕ НЕ ДОВОДИТЬ САМЕ ПО СОБІ.
-- Якщо корінь живе лише в НАШІЙ базі, ми теоретично могли б перерахувати весь ланцюг
-- після підміни. Тому корені щодня виносяться в ПУБЛІЧНИЙ репозиторій (O8), де історія
-- git видима й підробка означала б переписування публічної історії. Сторінка /verify
-- каже це прямо — обіцяти більше, ніж конструкція дає, було б тією самою накачаною
-- знижкою, тільки нашою.

CREATE TABLE IF NOT EXISTS day_seal (
  day          DATE PRIMARY KEY,
  rows_n       INTEGER NOT NULL,
  merkle_root  TEXT NOT NULL,
  prev_chain   TEXT,                       -- ланцюжок попередньої запечатаної доби
  chain        TEXT NOT NULL,              -- sha256(prev_chain || merkle_root)
  sealed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE day_seal IS
  'Печатка доби: корінь Меркла над снапшотами + ланцюжок. Незмінна за побудовою — '
  'інакше вона нічого не доводить.';

-- ⚠ Печатка мусить бути НЕЗМІННОЮ так само, як `price_snapshot` (інваріант A):
-- таблиця, яку можна переписати, доводить рівно нічого. Той самий механізм, що й для
-- снапшотів, — тригер із RAISE EXCEPTION.
CREATE OR REPLACE FUNCTION trg_seal_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'day_seal незмінна: печатка, яку можна переписати, нічого не доводить';
END;
$$;

DROP TRIGGER IF EXISTS seal_append_only ON day_seal;
CREATE TRIGGER seal_append_only
  BEFORE UPDATE OR DELETE ON day_seal
  FOR EACH ROW EXECUTE FUNCTION trg_seal_append_only();

CREATE INDEX IF NOT EXISTS ix_seal_day ON day_seal (day DESC);
