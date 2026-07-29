"""Запобіжники візуальної системи застосунку.

Народжено з S32/S33. Двічі поспіль замір показував те саме: система в проєкті Є,
а розмітка живе повз неї. У `Hapay.xaml` стояв коментар «типографічна шкала: рівно
чотири рівні» — і поруч 157 сирих `FontSize` у 15 значеннях. Радіусів було вісім,
чисел у відступах — 49.

Такі речі не ламають збірку й не видно в диффі одного файлу: кожен окремий
`Padding="13"` виглядає нормально. Видно їх лише в сумі — тобто тестом.

⚠ Тест НЕ вимірює краси. Він стежить рівно за одним: щоб нове значення бралося зі
шкали, а не вигадувалось на місці. Міняти шкалу можна — але тоді свідомо, тут.
"""
import os
import re
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app-maui")

# Шість кроків, ті самі, що --f1…--f6 у web/app.css. У розмітці — лише як
# {StaticResource F1..F6}; сире число означає, що хтось знову вгадав кегль.
SCALE_KEYS = {"F1", "F2", "F3", "F4", "F5", "F6"}

# Значок ПОРОЖНЬОГО СТАНУ — не текст, і в шкалу не входить (те саме рішення, що в
# app.css для .empty .ic). Єдиний дозволений сирий кегль, і саме тому — поіменно.
FONTSIZE_EXEMPT = {"56"}

# Крок 2px до 8 і 4px далі: нижче 8 різниця в один піксель справді видима (щільні
# рядки цін), вище 8 — ні.
SPACING_SCALE = {"0", "2", "4", "6", "8", "12", "16", "20", "24", "32", "40", "48"}

# Дві поверхні: 12 — картка/панель, 8 — дрібне. Ті самі --radius/--radius-s.
RADII = {"8", "12"}

SPACING_ATTRS = ("Padding", "Margin", "Spacing", "ColumnSpacing", "RowSpacing")


def _xaml():
    out = []
    for dp, _, fn in os.walk(APP):
        if "bin" in dp or "obj" in dp:
            continue
        for f in fn:
            if f.endswith(".xaml"):
                out.append(os.path.join(dp, f))
    return sorted(out)


def _views():
    """Розмітка сторінок. Словник ресурсів — окремо: саме він і оголошує палітру."""
    return [p for p in _xaml() if "Resources" not in p]


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _line(src, pos):
    return src[:pos].count("\n") + 1


def test_fontsize_comes_from_the_scale():
    """Сирий FontSize = кегль, вигаданий на місці. Ресурс не можна «майже вгадати»:
    або він є, або збірка падає."""
    bad = []
    for p in _views():
        src = _read(p)
        for m in re.finditer(r'FontSize="([^"]+)"', src):
            v = m.group(1)
            if v.startswith("{StaticResource "):
                key = v[len("{StaticResource "):].rstrip("}").strip()
                if key not in SCALE_KEYS:
                    bad.append(f"{os.path.basename(p)}:{_line(src, m.start())} FontSize={key} — поза шкалою")
            elif v not in FONTSIZE_EXEMPT:
                bad.append(f"{os.path.basename(p)}:{_line(src, m.start())} FontSize=\"{v}\" — сире число, візьми F1..F6")
    assert not bad, "\n".join(bad)


def test_spacing_comes_from_the_scale():
    """49 різних чисел у відступах — це не ритм, це шум. Відступ око читає як
    «охайно» сильніше за шрифт."""
    bad = []
    for p in _views():
        src = _read(p)
        for attr in SPACING_ATTRS:
            for m in re.finditer(rf'{attr}="([-\d.,\s]+)"', src):
                for part in m.group(1).split(","):
                    part = part.strip()
                    # від'ємні значення — навмисний трюк розкладки (виступ за межу),
                    # а не крок ритму; їх не чіпаємо
                    if part.startswith("-") or not part:
                        continue
                    if part not in SPACING_SCALE:
                        bad.append(f"{os.path.basename(p)}:{_line(src, m.start())} "
                                   f"{attr}=\"{m.group(1)}\" — {part} поза шкалою {sorted(SPACING_SCALE, key=int)}")
    assert not bad, "\n".join(sorted(set(bad)))


def test_no_hardcoded_colors_in_markup():
    """#1E888888 і рідня. Сірий з альфою працює в обох темах — але однаково блідо,
    тобто не правильно в жодній. Кольори живуть у Hapay.xaml, під кожну тему."""
    bad = []
    for p in _views():
        src = _read(p)
        for m in re.finditer(r'=\"(#[0-9A-Fa-f]{3,8})\"', src):
            bad.append(f"{os.path.basename(p)}:{_line(src, m.start())} {m.group(1)} — візьми токен із Hapay.xaml")
    assert not bad, "\n".join(bad)


def test_two_radii_only():
    """Було вісім різних скруглень. Око не розрізняє 10 і 12, але кожне зайве
    значення — це ще одне рішення, яке наступний розробник мусить вгадати."""
    bad = []
    for p in _xaml():
        src = _read(p)
        for rx in (r'CornerRadius="([\d.]+)"', r'RoundRectangle ([\d.]+)'):
            for m in re.finditer(rx, src):
                if m.group(1) not in RADII:
                    bad.append(f"{os.path.basename(p)}:{_line(src, m.start())} радіус {m.group(1)} — лише {sorted(RADII)}")
    assert not bad, "\n".join(bad)


def test_scale_is_declared_once():
    """Шкала мусить бути оголошена рівно в одному місці, інакше вона не шкала."""
    decl = collections.Counter()
    for p in _xaml():
        for m in re.finditer(r'<x:Double x:Key="(F[1-6])"', _read(p)):
            decl[m.group(1)] += 1
    missing = SCALE_KEYS - set(decl)
    dup = {k: n for k, n in decl.items() if n > 1}
    assert not missing, f"кроки шкали не оголошені: {sorted(missing)}"
    assert not dup, f"крок оголошено двічі: {dup}"


def _main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)
           and getattr(v, "__module__", None) == __name__]
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
