"""Інтеграційний тест колектора проти живого Timescale (§8.1). Skip-aware (CI).

Детерміновано: fetch підмінено на КАСЕТУ Pethouse (без живого HTTP). Перевіряє
повний конвеєр fetch→extract→persist→detect_pass: 9 снапшотів + scan_run +
declared-події (одиночний прогін = ще без 30-денної історії).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.dbguard import reset, test_dsn         # noqa: E402
URL = test_dsn("test_collect")                    # РУЙНІВНИЙ: нижче reset() дропає все

import psycopg                                    # noqa: E402
from db import migrate                            # noqa: E402
from collect import collect, SOURCES              # noqa: E402


def main():
    with psycopg.connect(URL, autocommit=True) as conn:
        reset(conn)
    migrate.apply(URL)

    def _read(name):
        with open(os.path.join(os.path.dirname(__file__), "cassettes", name), encoding="utf-8") as f:
            return f.read()
    cas_ph, cas_pc = _read("pethouse_akcii.html"), _read("petchoice_akcii.html")
    fetch = lambda url: cas_pc if "petchoice" in url else cas_ph   # DI: касета за URL, без HTTP

    checks, failed = [], 0
    with psycopg.connect(URL, autocommit=True) as conn:
        stats = collect(conn, SOURCES, fetch=fetch, delay=0)
        checks.append(("collect items = 12 (Pethouse 9 dedup + PetChoice 3)", stats["items"] == 12, stats))

        snaps = conn.execute("SELECT count(*) FROM price_snapshot").fetchone()[0]
        checks.append(("price_snapshot = 12", snaps == 12, snaps))

        sr = conn.execute("SELECT count(*), count(*) FILTER (WHERE surface='discovery') FROM scan_run").fetchone()
        checks.append(("2 discovery scan_run", sr == (2, 2), sr))

        ev = conn.execute("SELECT count(*), count(*) FILTER (WHERE badge_state='declared') "
                          "FROM discount_event").fetchone()
        checks.append(("11 подій, усі declared (8 PH + 3 PC)", ev == (11, 11), ev))

        ncats = conn.execute("SELECT count(DISTINCT sp.category_id) FROM store_product sp "
                             "JOIN category c USING (category_id) WHERE c.slug <> 'uncategorized'").fetchone()[0]
        checks.append(("товари розкладені по ≥2 реальних категоріях", ncats >= 2, ncats))

        # ── ізоляція джерел і чесний статус (T13) ────────────────────────────────
        # Було: виняток на одній крамниці вбивав увесь прохід разом із detect_pass,
        # а scan_run писався як 'ok' ще до роботи — провал виглядав успіхом.
        def boom(url):
            if "petchoice" in url:
                raise RuntimeError("імітація: крамниця лягла")
            return cas_ph

        st2 = collect(conn, SOURCES, fetch=boom, delay=0)
        ph = next(r for r in st2["per_source"] if r["source"] == "Pethouse")
        pc = next(r for r in st2["per_source"] if r["source"] == "PetChoice")
        checks.append(("падіння PetChoice НЕ завалило Pethouse",
                       ph["items"] == 9 and ph["status"] == "ok", (ph, pc)))
        checks.append(("PetChoice → failed, 0 позицій", pc["status"] == "failed" and pc["items"] == 0, pc))
        checks.append(("detect_pass відпрацював попри падіння джерела", st2["events"] >= 0, st2["events"]))
        checks.append(("проблемне джерело потрапило в problems",
                       [r["source"] for r in st2["problems"]] == ["PetChoice"], st2["problems"]))
        dbst = conn.execute("SELECT sr.status, sr.items_seen FROM scan_run sr "
                            "JOIN source s USING (source_id) WHERE s.name='PetChoice' "
                            "ORDER BY sr.scan_run_id DESC LIMIT 1").fetchone()
        checks.append(("scan_run у БД каже 'failed', а не 'ok' при нулі", dbst == ("failed", 0), dbst))

        # нуль без винятку (селектор помер / чужий HTML) — теж проблема, не тиша
        st3 = collect(conn, SOURCES, fetch=lambda u: cas_ph, delay=0)   # PetChoice дістає чужий HTML
        pc3 = next(r for r in st3["per_source"] if r["source"] == "PetChoice")
        checks.append(("мовчазний нуль (без винятку) видно в problems",
                       pc3["items"] == 0 and any(r["source"] == "PetChoice" for r in st3["problems"]), pc3))

    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {val!r}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
