"""Разовий перерахунок `store_product.mpn` наявним товарам за поточним матчером.

Навіщо окремий скрипт, а не міграція: логіка витягання артикула — регулярні вирази
в `matching.extract_mpn`, у SQL її не повторити чесно (а дублювати — значить розійтись).

Коли потрібен: після зміни правил матчингу. Інакше наявні рядки дістануть новий mpn
лише при наступному зборі того ж лістинга (repeat ~720 хв), тобто до півдоби товари
лежатимуть незгрупованими. Скрипт це прискорює.

Безпечно: `store_product` і так мутабельний — збір перезаписує mpn при кожному upsert
(ON CONFLICT DO UPDATE). Ідемпотентний: повторний запуск нічого не змінює.
Історію цін (append-only `price_snapshot`) НЕ чіпає.

Запуск на сервері (найпростіше — дати скрипту сам прочитати env-файл):
    /opt/hapay/venv/bin/python scripts/backfill_mpn.py --env-file /etc/hapay/hapay.env --dry-run
    /opt/hapay/venv/bin/python scripts/backfill_mpn.py --env-file /etc/hapay/hapay.env

Або якщо DATABASE_URL уже в середовищі (як у deploy.sh: `set -a; . env-файл; set +a`).
Свідомо НЕ радимо `grep|cut` — обрізає рядок на паролі з «=» і дає незрозумілий
psycopg-трейсбек замість помилки по суті.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg                                    # noqa: E402
from matching import extract_mpn                  # noqa: E402


def _load_env_file(path: str) -> None:
    """Мінімальний парсер KEY=VALUE (як `. file` у sh): коментарі, export, лапки."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, val = line.partition("=")          # partition — пароль може мати «=»
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            os.environ.setdefault(key.strip(), val)


def _mask(url: str) -> str:
    """URL без пароля — щоб діагностика не витікала в лог/чат."""
    import re
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", url)


def main() -> int:
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    if "--env-file" in argv:
        path = argv[argv.index("--env-file") + 1]
        if not os.path.exists(path):
            print(f"нема env-файлу: {path}", file=sys.stderr)
            return 1
        _load_env_file(path)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL не задано. Або передай --env-file /etc/hapay/hapay.env, "
              "або завантаж env як у deploy.sh: set -a; . /etc/hapay/hapay.env; set +a",
              file=sys.stderr)
        return 1
    if not url.startswith(("postgresql://", "postgres://")):
        print(f"DATABASE_URL не схожий на URI Postgres: {_mask(url)!r}\n"
              "Схоже, рядок обрізано (напр. `grep|cut` на паролі з «=»). "
              "Передай --env-file /etc/hapay/hapay.env — скрипт прочитає сам.",
              file=sys.stderr)
        return 1

    with psycopg.connect(url, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT store_product_id, title, mpn FROM store_product").fetchall()

        changes = [(spid, extract_mpn(title), old)
                   for spid, title, old in rows]
        changes = [(spid, new, old) for spid, new, old in changes if new != old]

        added = sum(1 for _, new, old in changes if old is None and new is not None)
        removed = sum(1 for _, new, old in changes if new is None and old is not None)
        altered = len(changes) - added - removed

        print(f"товарів у базі: {len(rows)}")
        print(f"зміниться:      {len(changes)}  (+{added} нових, ~{altered} змінених, "
              f"-{removed} знятих)")
        for spid, new, old in changes[:5]:
            print(f"   #{spid}: {old!r} → {new!r}")

        if dry:
            print("\n[--dry-run] нічого не записано")
            return 0
        if not changes:
            print("нема чого міняти")
            return 0

        with conn.cursor() as cur:
            cur.executemany("UPDATE store_product SET mpn = %s WHERE store_product_id = %s",
                            [(new, spid) for spid, new, _ in changes])

        grouped = conn.execute(
            "SELECT count(*) FROM (SELECT mpn FROM store_product WHERE mpn IS NOT NULL "
            "GROUP BY mpn HAVING count(DISTINCT source_id) > 1) g").fetchone()[0]
        print(f"\nоновлено: {len(changes)}")
        print(f"крос-крамничних груп тепер: {grouped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
