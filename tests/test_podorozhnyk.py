"""Golden-тест адаптера Подорожника на ОБРІЗАНІЙ касеті (§8.8).

Касета — 3 РЕАЛЬНІ товари зі стану сторінки (вбудований JSON): звичайний, знижковий
(price.max > current) і РЕЦЕПТУРНИЙ. Останній обов'язковий: адаптер мусить його
ПРОПУСТИТИ (restrictions.prescription), тож із трьох на виході рівно два.

Запуск:  python tests/test_podorozhnyk.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.podorozhnyk import PodorozhnykAdapter          # noqa: E402
from matching import pick_gtin                                # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "podorozhnyk_listing.html"), encoding="utf-8") as f:
        return PodorozhnykAdapter().extract(f.read())


def test_prescription_skipped():
    """3 товари в стані, один рецептурний → на виході 2. Рецептурне не показуємо."""
    items = _items()
    assert len(items) == 2, [i.title for i in items]
    assert len({i.external_ref for i in items}) == 2


def test_price_in_kopiykas_not_float():
    """Ціна — цілі копійки (інв. A): гривні×100, ніколи float у сховищі."""
    for i in _items():
        assert isinstance(i.price_now_kop, int) and i.price_now_kop > 0, i.price_now_kop
        assert i.price_old_kop is None or isinstance(i.price_old_kop, int)


def test_discount_old_price_only_when_higher():
    """price.max стає старою ціною ЛИШЕ коли вона вища за current; рівна — не знижка."""
    items = _items()
    disc = [i for i in items if i.price_old_kop is not None]
    plain = [i for i in items if i.price_old_kop is None]
    assert disc and plain, (len(disc), len(plain))       # у касеті є обидва
    for i in disc:
        assert i.price_old_kop > i.price_now_kop, (i.price_old_kop, i.price_now_kop)


def test_gtins_flow_and_validate():
    """Штрихкоди доходять до RawItem і дають валідний ключ через pick_gtin."""
    withgtin = [i for i in _items() if i.gtins]
    assert withgtin, "у реальних товарах Подорожника gtins мають бути"
    for i in withgtin:
        assert pick_gtin(i.gtins) is not None, i.gtins       # валідний GTIN-14


def test_ref_is_path_only():
    for i in _items():
        assert i.external_ref.startswith("/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


def test_image_is_pointer_only():
    """Інваріант B: фото — вказівник (hotlink), ніколи байти."""
    for i in _items():
        if i.image_url is not None:
            assert i.image_url.startswith("https://"), i.image_url
            assert not i.image_url.startswith("data:")


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
