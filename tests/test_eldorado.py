"""Golden-тести адаптера Eldorado на РЕАЛЬНІЙ (обрізаній) касеті лістинга.

Головні пастки, які тут перевіряються:
  1. блок розстрочки «від 1 200 грн.» лежить поруч із ціною — його не можна брати
     за ціну (parse_price_to_kop зчитав би його як 1200);
  2. позиції «Продано»/«Незабаром» цін не мають — їх треба пропускати, а не писати 0;
  3. класи хешовані (styled-components) — селектори мусять лишатись префіксними.

Запуск:  python tests/test_eldorado.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.eldorado import EldoradoAdapter          # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes", "eldorado_listing.html")


def _items():
    with open(CAS, encoding="utf-8") as f:
        return EldoradoAdapter().extract(f.read())


def test_extracts_only_priced_positions():
    """У касеті 3 картки; «Продано» (без ціни) не має потрапити у вихід."""
    items = _items()
    assert len(items) == 2, [i.title for i in items]
    assert all(i.price_now_kop for i in items)


def test_discount_card_prices():
    it = next(i for i in _items() if i.external_ref == "p71477703")
    assert it.price_now_kop == 999900          # 9 999 грн
    assert it.price_old_kop == 1099900         # 10 999 грн
    assert it.discount_pct == 9
    assert it.title == "Смартфон OPPO Reno 12 FS 8/512GB cірий"


def test_plain_card_has_no_old_price():
    it = next(i for i in _items() if i.external_ref == "p71474996")
    assert it.price_now_kop == 719900          # 7 199 грн
    assert it.price_old_kop is None
    assert it.discount_pct is None


def test_installment_is_not_taken_as_price():
    """Поруч із 7 199 лежить «від 1 200 грн.» (розстрочка) — вона НЕ мусить стати ціною."""
    it = next(i for i in _items() if i.external_ref == "p71474996")
    assert it.price_now_kop != 120000
    assert all(i.price_now_kop != 120000 for i in _items())


def test_sold_out_position_skipped():
    """iPhone 15 Pro у касеті має статус «Продано» і кнопку «Повідомити» — без ціни."""
    assert all("MTUX3RX" not in i.title for i in _items())


def test_url_absolute_and_ref_is_product_id():
    """external_ref = id товару (не слаг і не мовний префікс): слаг крамниця може
    переписати, а /uk/ ↔ без нього — те саме."""
    for it in _items():
        assert it.url.startswith("https://eldorado.ua/uk/")
        assert it.external_ref.startswith("p") and it.external_ref[1:].isdigit()
        assert it.external_ref[1:] in it.url


def test_no_image_bytes_or_wrong_host():
    """Фото в лістингу немає (малює скрипт) → None. Головне — не підсунути чужий URL."""
    for it in _items():
        assert it.image_url is None


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
