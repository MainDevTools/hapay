"""Запобіжники сайту: те, що ламається МОВЧКИ й видно лише в браузері.

Народжений з 2026-07-27: каталог у Telegram Mini App був порожньою сторінкою, і жоден
тест цього не бачив, бо ламалось воно в рантаймі браузера. Ланцюг був такий:

    renderHeader()  у Telegram ВИДАЛЯЄ #hdr
    catalog.html    наступним рядком робив getElementById('hdr').outerHTML = …
                    → TypeError валить увесь інлайн-скрипт
                    → `const _sect` лишається в TDZ
    catalog.js      падає на `typeof _sect` (typeof НЕ рятує від TDZ)
                    → ні load(), ні renderChips() — 0 карток, body.innerText = ""

Три перевірки нижче ловлять кожну ланку окремо, без браузера. Це той самий клас, що
`test_sqlsafe`: дешевий текстовий запобіжник проти помилки, яка інакше проявляється
далеко від причини.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _read(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


# Запобіжник має читати КОД, а не прозу про код: перша ж версія цього файлу спіймала
# власний коментар, у якому описано полагоджену помилку. Коментарі, що пояснюють
# «чому так не можна», мусять лишатись у файлі й не спрацьовувати як порушення.
_STRIP = [
    re.compile(r"<!--.*?-->", re.S),      # HTML
    re.compile(r"/\*.*?\*/", re.S),       # CSS і JS блокові
    re.compile(r"(?m)^\s*//.*$"),         # JS рядкові (лише з початку рядка: у
]                                         # середині рядка живуть https:// в адресах


def _blank(m):
    """Замість коментаря — пробіли, щоб номери рядків не з'їхали."""
    return re.sub(r"[^\n]", " ", m.group(0))


def _code(name):
    """Текст без коментарів, зі збереженням позицій рядків."""
    src = _read(name)
    for rx in _STRIP:
        src = rx.sub(_blank, src)
    return src


def _pages():
    return sorted(n for n in os.listdir(WEB) if n.endswith(".html"))


# ── 1. #hdr належить лише renderHeader ────────────────────────────────────────────
def test_pages_do_not_touch_hdr():
    """У Telegram renderHeader видаляє #hdr. Будь-яке звертання до нього зі сторінки —
    або мертвий код, або TypeError; ловимо і те, і те."""
    for page in _pages():
        src = _code(page)
        for m in re.finditer(r"getElementById\(\s*['\"]hdr['\"]\s*\)", src):
            line = src[:m.start()].count("\n") + 1
            raise AssertionError(
                f"{page}:{line} звертається до #hdr. У Mini App його вже немає — "
                f"renderHeader() його видаляє. Малюй у власний контейнер.")


# ── 2. усе, що JS розіменовує без перевірки, мусить бути в розмітці ───────────────
_DEREF = re.compile(r"document\.getElementById\(\s*['\"]([\w-]+)['\"]\s*\)\s*\.")


def _ids_in(html):
    return set(re.findall(r'\bid="([\w-]+)"', html))


def test_unguarded_ids_exist_in_markup():
    """`getElementById('x').щось` без перевірки на null: якщо такого id в розмітці
    немає — сторінка помре на першому ж рядку, і далі не виконається НІЧОГО.
    Саме так catalog.js замовк цілком через відсутній #sort."""
    pairs = [("catalog.js", "catalog.html"), ("app.js", None)]
    for js, page in pairs:
        src = _code(js)
        wanted = set(_DEREF.findall(src))
        if page:                       # catalog.js живе лише на одній сторінці
            have = _ids_in(_read(page))
            missing = wanted - have
            assert not missing, f"{js} розіменовує без перевірки {sorted(missing)}, а в {page} їх немає"
        else:                          # app.js спільний: id має бути хоч на одній сторінці
            have = set().union(*(_ids_in(_read(p)) for p in _pages()))
            missing = wanted - have
            assert not missing, f"{js} розіменовує без перевірки {sorted(missing)} — немає в жодній сторінці"


# ── 3. кожен var(--token) мусить бути оголошений ──────────────────────────────────
_DECL = re.compile(r"(--[\w-]+)\s*:")
_USE = re.compile(r"var\(\s*(--[\w-]+)")


def test_all_css_vars_declared():
    """Прибрані --green/--amber (0 використань, спадок кольору-вердикту, скасованого
    T12) не мають повернутись через недогляд, а друкарська помилка в назві токена
    інакше просто дає порожнє значення — без жодної скарги браузера."""
    css = _read("app.css")
    declared = set(_DECL.findall(css))
    # інлайнові <style> сторінок можуть оголошувати власні
    for page in _pages():
        declared |= set(_DECL.findall(_read(page)))
    # var(--x, запас) із запасним значенням — законний спосіб узяти змінну, яку
    # виставляє JS у рантаймі (так живе --chart-h). Без запасу — це просто пусто.
    no_fallback = set()
    for name in ["app.css", "app.js", "catalog.js"] + _pages():
        for m in re.finditer(r"var\(\s*(--[\w-]+)\s*([,)])", _read(name)):
            if m.group(2) == ")":
                no_fallback.add(m.group(1))
    unknown = {u for u in no_fallback if u not in declared}
    assert not unknown, f"використані без запасного значення й не оголошені: {sorted(unknown)}"


def test_no_dead_tokens():
    """Зворотний бік: оголошене, але ніде не вжите — сміття в палітрі, яке запрошує
    повернути скасоване рішення (саме так жили --green/--amber до 2026-07-27)."""
    css = _read("app.css")
    declared = set(_DECL.findall(css))
    used = set()
    for name in ["app.css", "app.js", "catalog.js"] + _pages():
        used |= set(_USE.findall(_read(name)))
    dead = {d for d in declared if d not in used}
    assert not dead, f"оголошені, але ніде не вжиті токени: {sorted(dead)}"


# ── 4. медіа-запит не додає специфічності ────────────────────────────────────────
_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _rules(css):
    """(порядок, у_медіа, селектор, властивість).

    ⚠ Перша версія цього парсера мовчки не бачила НІЧОГО в медіа-блоках, тож
    перевірка нижче була зеленою з хибної причини — рівно той дефект, який у цьому
    проєкті вже ловили тричі. Тому і сам запобіжник перевіряється на зламаному
    входженні (див. Outcome задачі)."""
    css = _COMMENT.sub("", css)
    out, pos, order, media, head_start = [], 0, 0, 0, 0
    n = len(css)
    while pos < n:
        ch = css[pos]
        if ch == "{":
            head = css[head_start:pos].strip()
            if head.startswith("@media"):
                media += 1
                pos += 1
                head_start = pos
                continue
            if head.startswith("@"):            # @keyframes тощо — тіло пропускаємо
                depth = 1
                pos += 1
                while pos < n and depth:
                    depth += (css[pos] == "{") - (css[pos] == "}")
                    pos += 1
                head_start = pos
                continue
            end = css.find("}", pos)
            if end < 0:
                break
            body = css[pos + 1:end]
            for sel in head.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                for decl in body.split(";"):
                    if ":" not in decl:
                        continue
                    prop = decl.split(":", 1)[0].strip()
                    if not prop or prop.startswith("--"):
                        continue
                    out.append((order, media > 0, sel, prop))
                    order += 1
            pos = end + 1
            head_start = pos
            continue
        if ch == "}":
            media = max(0, media - 1)
            pos += 1
            head_start = pos
            continue
        pos += 1
    return out


def test_media_rules_not_overridden_by_later_base():
    """@media НЕ додає специфічності. Правило, написане в медіа-запиті, програє
    однаковому за селектором базовому правилу, якщо те стоїть НИЖЧЕ у файлі.
    Двічі наступив на це власноруч: підвал не з'являвся (26.07), навігація на
    планшеті лишалась схованою (27.07) — обидва рази помилку видно лише в браузері."""
    rules = _rules(_code("app.css"))
    in_media = [(o, s, p) for o, m, s, p in rules if m]
    base = [(o, s, p) for o, m, s, p in rules if not m]
    bad = []
    for mo, ms, mp in in_media:
        for bo, bs, bp in base:
            if bo > mo and bs == ms and bp == mp:
                bad.append(f"{ms} {{{mp}}}: базове правило нижче (позиція {bo}) переб'є медіа-правило (позиція {mo})")
    assert not bad, "\n".join(sorted(set(bad)))


# ── 5. клікабельне мусить бути кнопкою або посиланням ────────────────────────────
_CLICKABLE = ("chip", "catlink", "title", "cmp")


def test_no_div_controls():
    """<div onclick> — це елемент, до якого не веде Tab і якого не бачить читач екрана.

    Саме так до 2026-07-27 жили чіпи, 149 категорій і назва товару: каталог був
    непридатний без миші, а краулер не мав жодного посилання на товар. Перевірка
    текстова, бо розмітку будує JS: шукаємо `<div class="chip"` і рідню."""
    for js in ("catalog.js", "app.js"):
        src = _code(js)
        for cls in _CLICKABLE:
            for m in re.finditer(rf'<div[^>]*class="{cls}\b', src):
                line = src[:m.start()].count("\n") + 1
                raise AssertionError(
                    f"{js}:{line} малює <div class=\"{cls}\">. Керування мусить бути "
                    f"<button> або <a href>, інакше воно недосяжне з клавіатури.")
    # у сторінках теж
    for page in _pages():
        src = _code(page)
        for cls in _CLICKABLE:
            assert f'<div class="{cls}"' not in src and f"<div class='{cls}'" not in src, \
                f"{page}: <div class=\"{cls}\"> — має бути <button>/<a>"


# ── 6. один <h1> на документ ─────────────────────────────────────────────────────
# Внутрішня адмінка свідомо поза спільною системою: це не публічна поверхня, і
# тягнути в неї сайтові стилі означало б ризикувати робочим інструментом заради
# вигляду, якого ніхто, крім оператора, не бачить.
_INTERNAL = {"admin.html"}


def test_single_h1_per_document():
    """Шапка малює бренд на КОЖНІЙ сторінці. Поки він був <h1>, кожна сторінка з
    власним заголовком мала два h1 (заміряно 2026-07-29: 11 сторінок). Це не лише
    семантика — 21px бренду й 31px заголовка сперечались за один рівень ієрархії,
    і сторінка не мала однієї головної думки."""
    from_header = len(re.findall(r"<h1[\s>]", _code("app.js")))
    assert from_header == 0, (
        f"app.js малює {from_header} <h1> у спільній шапці — тоді на кожній сторінці "
        f"з власним заголовком їх буде два. Бренд — це підпис поверхні, а не заголовок.")
    for page in _pages():
        # Адмінка — два h1 у ВЗАЄМОВИКЛЮЧНИХ екранах (форма входу / панель під `hidden`),
        # тобто одночасно доступний рівно один. Плюс вона поза спільною системою: свій
        # <style>, свій layout, не публічна поверхня.
        if page in _INTERNAL:
            continue
        n = len(re.findall(r"<h1[\s>]", _code(page)))
        assert n <= 1, f"{page}: {n} тегів <h1> на одну сторінку"


# ── 7. публічна сторінка живе у спільній системі ─────────────────────────────────
_PALETTE = ("--accent", "--bg", "--surface", "--fg", "--line")


def test_public_pages_share_the_stylesheet():
    """До 2026-07-29 /privacy, /terms і /support не підключали app.css узагалі: кожна
    несла ВЛАСНУ копію системи з акцентом #512BD4 (фіолетовий зі шаблону MAUI), тілом
    16px/1.6 і власним темним фоном. І при цьому всі три лінкувались із підвалу кожної
    сторінки — тобто «Конфіденційність» відкривала візуально інший сайт."""
    for page in _pages():
        if page in _INTERNAL:
            continue
        src = _read(page)
        assert "/s/app.css" in src, f"{page} не підключає спільні стилі"
        # власний <style> дозволений (компоненти сторінки), але НЕ перевизначення палітри
        own = re.findall(r"<style>(.*?)</style>", src, re.S)
        for block in own:
            for tok in _PALETTE:
                assert not re.search(rf"{tok}\s*:", block), (
                    f"{page} перевизначає {tok} у власному <style> — це друга палітра, "
                    f"яка розійдеться з app.css")


# ── 8. два атрибути class в одному тезі ──────────────────────────────────────────
_TAG = re.compile(r"<[a-zA-Z][^>]*>", re.S)


def test_no_duplicate_class_attribute():
    """Браузер бере ПЕРШИЙ class і мовчки викидає другий — стиль просто не діє, і
    жодної скарги ніде. Народжено 2026-07-29: власна пакетна заміна інлайн-стилів на
    класи додала другий class у три теги, і всі три виглядали правильними в диффі."""
    for page in _pages():
        src = _read(page)
        for m in _TAG.finditer(src):
            if len(re.findall(r"\bclass=", m.group(0))) > 1:
                line = src[:m.start()].count("\n") + 1
                raise AssertionError(
                    f"{page}:{line} має два атрибути class — діє лише перший: "
                    f"{' '.join(m.group(0).split())[:100]}")


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
