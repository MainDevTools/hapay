"""Тести ядра PC-колектора `run_pass` — чисті, БЕЗ мережі (фейковий клієнт).

Головне, що стережемо: помилка ОДНІЄЇ задачі не валить прохід (крихкість емулятора
починалась саме з того, що один збій зупиняв увесь збір), і що PC бере лише fetch.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from pc_collector import run_pass          # noqa: E402


class FakeClient:
    def __init__(self, tasks, fetch_errors=None):
        self._tasks = tasks
        self.fetch_errors = fetch_errors or {}     # url -> Exception
        self.lease_calls, self.ingested, self.failed, self.fetched = [], [], [], []

    def lease(self, limit, modes):
        self.lease_calls.append((limit, tuple(modes)))
        return self._tasks

    def fetch(self, url):
        self.fetched.append(url)
        if url in self.fetch_errors:
            raise self.fetch_errors[url]
        return f"<html>{url}</html>"

    def ingest(self, source, url, html, task_id):
        self.ingested.append((source, url, task_id))

    def fail(self, task_id, note):
        self.failed.append((task_id, note))


def _task(tid, src, url, mode="fetch"):
    return {"task_id": tid, "source": src, "url": url, "mode": mode}


def test_lease_asks_only_fetch_mode():
    """PC мусить просити ЛИШЕ fetch — інакше вкраде render-задачі в телефона."""
    c = FakeClient([_task(1, "Foxtrot", "https://f/a")])
    run_pass(c, polite=lambda: None)
    assert c.lease_calls[0][1] == ("fetch",), c.lease_calls


def test_success_fetches_and_ingests():
    c = FakeClient([_task(1, "Foxtrot", "https://f/a"), _task(2, "Moyo", "https://m/b")])
    ok, failed = run_pass(c, polite=lambda: None)
    assert (ok, failed) == (2, 0)
    assert {t[2] for t in c.ingested} == {1, 2}
    assert not c.failed


def test_one_error_does_not_stop_the_pass():
    """Задача A падає на fetch → collect/fail; задача B все одно збирається.
    Це і є те, чого бракувало емулятору — один збій не зупиняє все."""
    c = FakeClient(
        [_task(1, "Foxtrot", "https://f/bad"), _task(2, "Moyo", "https://m/ok")],
        fetch_errors={"https://f/bad": TimeoutError("timed out")})
    ok, failed = run_pass(c, polite=lambda: None)
    assert (ok, failed) == (1, 1)
    assert c.failed and c.failed[0][0] == 1 and "TimeoutError" in c.failed[0][1]
    assert c.ingested == [("Moyo", "https://m/ok", 2)]   # B зібрано попри збій A


def test_render_task_skipped():
    """Захист: якщо в оренду просочилась render-задача — GET-ом її НЕ тягнемо."""
    c = FakeClient([_task(1, "Comfy", "https://c/x", mode="render")])
    ok, failed = run_pass(c, polite=lambda: None)
    assert (ok, failed) == (0, 0)
    assert not c.fetched and not c.ingested and not c.failed


def test_empty_lease_is_noop():
    c = FakeClient([])
    assert run_pass(c, polite=lambda: None) == (0, 0)


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
