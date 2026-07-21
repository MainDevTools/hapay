"""Golden-тест адаптера Венкона на ДВОХ обрізаних касетах (§8.8), по 3 картки кожна.

Дві касети, а не одна, бо Венкон розмічає schema.org НЕ ВСІ розділи: пилососи мають
мікродані, кондиціонери — ті самі картки без жодного `itemprop`. Адаптер мусить
читати обидві розкладки, тож обидві й перевіряємо. З однією касетою половина коду
лишилась би неперевіреною — і саме та половина, що тримає кондиціонери, бойлери й
блендери, заради яких крамницю й заводили.

Запуск:  python tests/test_vencon.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.vencon import VenconAdapter                # noqa: E402
from matching import extract_mpn                          # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items(name):
    with open(os.path.join(CAS, name), encoding="utf-8") as f:
        return VenconAdapter().extract(f.read())


def _micro():
    return _items("vencon_listing.html")


def _plain():
    return _items("vencon_listing_plain.html")


def test_both_layouts_yield_items():
    assert len(_micro()) == 3, _micro()
    assert len(_plain()) == 3, _plain()


def test_microdata_price_and_old_price():
    """Розділ із розміткою: ціну беремо з meta[itemprop=price], стару — з .old-price."""
    i = next(x for x in _micro() if "fc9334" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (739900, 849900), (i.price_now_kop, i.price_old_kop)


def test_plain_layout_reads_visible_price():
    """Розділ БЕЗ розмітки: ціна читається з видимого `.product-price .actual`.

    Тут ламався б адаптер, що вміє лише мікродані, — тихо, віддаючи нуль товарів.
    """
    i = next(x for x in _plain() if "osaka" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (1566000, 1740000), (i.price_now_kop, i.price_old_kop)


def test_title_from_attribute_not_glued_text():
    """Назва склеєна в тексті («ПылесосBosch»), тож беремо атрибут title посилання."""
    i = next(x for x in _micro() if "bgs05a220" in x.external_ref)
    assert i.title == "Пылесос Bosch BGS05A220", i.title
    assert extract_mpn(i.title) == "BGS05A220"


def test_spec_labels_not_mistaken_for_products():
    """`itemprop=name` є ще й на кнопці «Купить» та на КОЖНОМУ підписі характеристики.
    Якби картки бралися по ньому, у видачу лізли б «Уровень шума, дБ» і «Купить»."""
    bad = {"Купить", "Питание", "Мощность, Вт", "Уровень шума, дБ", "Тип уборки"}
    assert not ({i.title for i in _micro()} & bad)
    assert all(len(i.title) > 12 for i in _micro() + _plain())


def test_ref_is_path_only():
    for i in _micro() + _plain():
        assert i.external_ref.startswith("/products/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


def test_image_is_absolute_pointer():
    """Інваріант B: фото — вказівник, ніколи байти. src у крамниці відносний → добудовуємо."""
    for i in _micro() + _plain():
        assert i.image_url and i.image_url.startswith("https://vencon.ua/"), i.image_url
        assert not i.image_url.startswith("data:")


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
