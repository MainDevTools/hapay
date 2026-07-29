"""Дерево Меркла: доказ мусить ЛАМАТИСЯ від підміни (S31).

Тест не про «функція повертає рядок», а про єдину властивість, заради якої вся
конструкція існує: **підроблене спостереження не проходить перевірку**. Якщо це
не так — печатка декоративна, а сторінка /verify обіцяє те, чого немає.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import merkle  # noqa: E402


def _leaves(n):
    return [merkle.leaf(i, 10000 + i * 7, None if i % 2 else 9999, i % 3 != 0,
                        f"2026-07-20T10:{i:02d}:00+00:00") for i in range(n)]


def test_proof_valid_for_every_leaf():
    """Кожен лист мусить доводитись — включно з непарними розмірами, де останній
    вузол дублюється сам із собою (класичне місце помилки в реалізаціях)."""
    for n in (1, 2, 3, 5, 7, 8, 16, 33):
        ls = _leaves(n)
        root = merkle.root(ls)
        for i in range(n):
            assert merkle.verify(ls[i], merkle.proof(ls, i), root), f"n={n}, i={i}"


def test_tampered_leaf_fails():
    ls = _leaves(9)
    root = merkle.root(ls)
    fake = merkle.leaf(3, 1, None, True, "2026-07-20T10:03:00+00:00")   # інша ціна
    assert not merkle.verify(fake, merkle.proof(ls, 3), root)


def test_tampered_path_fails():
    """Підміна сусіда в шляху теж мусить провалюватись — інакше доказ можна підігнати."""
    ls = _leaves(9)
    root = merkle.root(ls)
    path = merkle.proof(ls, 4)
    path[0] = {"side": path[0]["side"], "hash": "0" * 64}
    assert not merkle.verify(ls[4], path, root)


def test_side_matters():
    """Якщо переплутати бік конкатенації — доказ не сходиться. Саме тому `side`
    їде в API: без нього перевіряльник не знає порядку."""
    ls = _leaves(4)
    root = merkle.root(ls)
    path = [{"side": "left" if p["side"] == "right" else "right", "hash": p["hash"]}
            for p in merkle.proof(ls, 0)]
    assert not merkle.verify(ls[0], path, root)


def test_leaf_format_is_stable():
    """Формат листа — ПУБЛІЧНИЙ КОНТРАКТ: люди перевірятимуть ним свої ціни. Зміна
    «на місці» зламає всі попередні докази, тому значення прибите цвяхом."""
    got = merkle.leaf(42, 199900, 249900, True, "2026-07-20T10:00:00+00:00")
    assert got == merkle.leaf(42, 199900, 249900, True, "2026-07-20T10:00:00+00:00")
    # порожня стара ціна кодується порожнім рядком, не «None»
    a = merkle.leaf(42, 199900, None, True, "2026-07-20T10:00:00+00:00")
    assert "None" not in str(a) and len(a) == 64


def test_chain_breaks_on_old_day_change():
    """Підміна ДАВНЬОЇ доби мусить ламати всі наступні ланки — інакше ланцюжок
    декоративний."""
    d1, d2 = merkle.root(_leaves(4)), merkle.root(_leaves(6))
    c1 = merkle.chain(None, d1)
    c2 = merkle.chain(c1, d2)
    tampered_c1 = merkle.chain(None, merkle.root(_leaves(5)))     # інша перша доба
    assert merkle.chain(tampered_c1, d2) != c2


def test_empty_day_still_sealed():
    """Доба без спостережень теж має корінь: «нічого не було» — теж твердження."""
    assert len(merkle.root([])) == 64


def _main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)
           and getattr(v, "__module__", None) == __name__]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL  {fn.__name__}  -> {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
