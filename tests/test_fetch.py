"""Тест розпаковки тіла відповіді (`collect.decode_body`). Без БД і без HTTP.

Навіщо: stdlib `urllib` не розпаковує сам, тому ми довго слали `Accept-Encoding: identity`
й качали вдев'ятеро більше байтів (виміряно: 988 КБ → 112 КБ, 8.8×). Це різниця між
138 ТБ/міс і 15.7 ТБ/міс на 2.5 млн товарів — тобто між «неможливо» і «базовий тариф».

Ціна помилки тут висока й тиха: якщо розпакувати неправильно, парсер отримає бінарне
сміття, знайде 0 позицій — і це виглядатиме як «у крамниці нема акцій» (T13).

Запуск:  python tests/test_fetch.py
"""
import gzip
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collect import decode_body  # noqa: E402

HTML = "<html><body><h1>Ціна 1 700,00 ₴ — Royal Canin</h1></body></html>"
RAW = HTML.encode("utf-8")


def test_gzip_roundtrip():
    assert decode_body(gzip.compress(RAW), "gzip") == HTML


def test_deflate_zlib_wrapped():
    assert decode_body(zlib.compress(RAW), "deflate") == HTML


def test_deflate_raw_no_wrapper():
    """Частина серверів шле сирий deflate без zlib-заголовка — теж мусимо взяти."""
    co = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    body = co.compress(RAW) + co.flush()
    assert decode_body(body, "deflate") == HTML


def test_identity_passthrough():
    assert decode_body(RAW, "identity") == HTML


def test_missing_header_is_plain():
    """Сервер може проігнорувати наше прохання і віддати нестиснуте — без заголовка."""
    assert decode_body(RAW, None) == HTML


def test_header_case_and_spaces():
    assert decode_body(gzip.compress(RAW), "  GZIP  ") == HTML


def test_ukrainian_survives():
    """Кирилиця й ₴ мусять пережити цикл — інакше парсер цін мовчки зламається."""
    out = decode_body(gzip.compress(RAW), "gzip")
    assert "Ціна" in out and "₴" in out and "1 700,00" in out


def test_broken_gzip_raises_not_returns_garbage():
    """Гучно падаємо, а не віддаємо сміття: тиха 0-видача = «ok» при поламаному зборі."""
    try:
        decode_body(b"this is definitely not gzip", "gzip")
    except Exception:
        return
    raise AssertionError("мала бути помилка, а не мовчазне сміття")


def test_real_compression_ratio_is_worth_it():
    """Санітарна перевірка передумови: HTML тисне в рази, інакше вся затія марна."""
    big = (HTML * 200).encode("utf-8")
    assert len(gzip.compress(big)) * 5 < len(big)


def _main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v) and getattr(v, "__module__", None) == __name__]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
