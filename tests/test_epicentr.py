"""Golden-тест адаптера Епіцентру на ОБРІЗАНІЙ касеті (§8.8): 3 реальні картки лістингу.

Особливість крамниці — екстракція йде РОЗМІТКОЮ schema.org, а не класами: класи в
Епіцентрі хешовані Nuxt-ом (`_Al-5uY1o`) і міняються з кожним білдом їхнього фронту.

Головне, що тут стережемо, — пастка подвійного `itemprop="price"`: перекреслена СТАРА
ціна розмічена тим самим itemprop, що й поточна. Селектор без розрізнення за
`data-product-price-main` / `-old` брав би стару ціну як поточну ТИХО, без помилки, і
ми рахували б знижки від неправильного числа.

Запуск:  python tests/test_epicentr.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.epicentr import EpicentrAdapter            # noqa: E402
from matching import extract_mpn                          # noqa: E402

CAS = os.path.join(os.path.dirname(__file__), "cassettes")


def _items():
    with open(os.path.join(CAS, "epicentr_listing.html"), encoding="utf-8") as f:
        return EpicentrAdapter().extract(f.read())


def test_extract_counts():
    items = _items()
    assert len(items) == 3, len(items)
    assert len({i.external_ref for i in items}) == 3


def test_old_price_not_mistaken_for_current():
    """Картка зі знижкою: поточна 65 499, стара 72 777 — саме в цьому порядку.

    Якби селектор брав перший-ліпший `itemprop=price`, поточна вийшла б 72 777.
    """
    i = next(x for x in _items() if "victus-15-fa2009ua" in x.external_ref)
    assert i.price_now_kop == 6549900, i.price_now_kop
    assert i.price_old_kop == 7277700, i.price_old_kop
    assert extract_mpn(i.title) == "BV8X3EA"


def test_no_discount_leaves_old_empty():
    """Без знижки зони `-old` в картці немає → стара ціна None, а не «дорівнює поточній»."""
    i = next(x for x in _items() if "al15-41p-r4l1" in x.external_ref)
    assert (i.price_now_kop, i.price_old_kop) == (2599900, None)


def test_ref_is_path_not_full_url():
    """external_ref — шлях без домену й хвостів (§4.8), щоб не плодити дублі."""
    for i in _items():
        assert i.external_ref.startswith("/ua/shop/"), i.external_ref
        assert "?" not in i.external_ref and "#" not in i.external_ref


def test_image_is_pointer_only():
    """Інваріант B: фото — ВКАЗІВНИК, ніколи байти. data:-URI не приймаємо."""
    for i in _items():
        assert i.image_url and i.image_url.startswith("http"), i.image_url
        assert not i.image_url.startswith("data:")


def test_mpn_present_for_matching():
    """MPN у дужках назви — основа матчингу T15 («Де купити»)."""
    mpns = {extract_mpn(i.title) for i in _items()}
    assert None not in mpns, mpns


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} перевірок пройдено")


if __name__ == "__main__":
    _main()
