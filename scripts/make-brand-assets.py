"""Генератор брендових зображень: favicon + картка для прев'ю посилань (og:image).

Запускати вручну після зміни фірмового стилю; результат КОМІТИТЬСЯ у `web/`, тож
серверу Pillow не потрібен — він лише віддає готові файли.

⚠ Чому картинка НАША, а не фото товару (інваріант B). Соцмережі не просто показують
`og:image` — вони ЗАВАНТАЖУЮТЬ його й кешують у себе. Підставити туди фото крамниці
означало б спричинити копіювання чужих байтів на чужі сервери нашими руками. Тир
«hotlink» такого не покриває: hotlink — це коли байти йде брати БРАУЗЕР читача.
Тому в прев'ю — власна графіка з фактами, які ми й так публікуємо (назва, ціна).
Питання «чи можна фото товару в прев'ю» — юридичне, тобто 🧭 оператора.

    python scripts/make-brand-assets.py
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")

GREEN = (26, 129, 60)          # --accent світлої теми (той самий, що на сайті)
INK = (20, 22, 26)             # --fg
MUTED = (95, 102, 114)         # --muted
BG = (244, 245, 247)           # --bg
WHITE = (255, 255, 255)

FONTS = [r"C:\Windows\Fonts\arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
FONTS_REG = [r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def _font(paths, size):
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise SystemExit("не знайдено шрифту з кирилицею: " + ", ".join(paths))


def favicon():
    """Зелений квадрат із білою «Х». Лінію ціни на 16px не видно — літера читається."""
    sizes = [16, 32, 48, 64, 128, 256]
    imgs = []
    for s in sizes:
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        r = max(2, round(s * 0.22))
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=GREEN)
        f = _font(FONTS, round(s * 0.68))
        box = d.textbbox((0, 0), "Х", font=f)
        d.text(((s - (box[2] - box[0])) / 2 - box[0],
                (s - (box[3] - box[1])) / 2 - box[1]), "Х", font=f, fill=WHITE)
        imgs.append(im)
    out = os.path.join(WEB, "favicon.ico")
    imgs[-1].save(out, format="ICO", sizes=[(s, s) for s in sizes])
    imgs[1].save(os.path.join(WEB, "icon-32.png"))
    imgs[-2].save(os.path.join(WEB, "icon-180.png"))     # apple-touch-icon
    return out


def og_card():
    """1200×630 — розмір, який очікують Telegram/Facebook/X.

    Вміст навмисно про ПРОДУКТ, не про товар: назва, обіцянка й лінія ціни зі
    статутною базою. Та сама картинка йде до кожного посилання, тож вона не має
    стверджувати нічого про конкретний товар."""
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # ── лінія ціни зі статутною базою ──────────────────────────────────────────
    # ⚠ Картинка мусить бути ПРАВДИВОЮ за власною формулою: пунктир — найменша ціна
    # за 30 днів, отже жодна історична точка не може лежати НИЖЧЕ за нього. Перша
    # версія цього малюнка тричі пірнала під базу — тобто ілюстрація до Omnibus
    # порушувала Omnibus. Нижче за пунктир іде лише фінальне зниження: саме воно й
    # робить знижку справжньою.
    BASE = 442                                           # y бази; більший y = нижча ціна
    hist = [(90, 342), (230, 380), (370, 358), (510, BASE), (650, 402), (790, 386)]
    drop = [(930, 508), (1110, 508)]
    pts = hist + drop
    step = []
    for i, (x, y) in enumerate(pts):                     # сходинки, не інтерполяція (T12)
        if i:
            step.append((x, pts[i - 1][1]))
        step.append((x, y))
    d.line([(90, 560), (1110, 560)], fill=(214, 218, 224), width=2)
    d.line(step, fill=GREEN, width=7, joint="curve")
    for x, y in pts:
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=GREEN)
    for x in range(90, 1111, 22):                        # база 30 днів — пунктир
        d.line([(x, BASE), (x + 11, BASE)], fill=MUTED, width=3)

    f_brand = _font(FONTS, 96)
    f_lead = _font(FONTS_REG, 40)
    f_note = _font(FONTS_REG, 28)
    d.text((88, 92), "Хапай", font=f_brand, fill=INK)
    d.text((92, 208), "знижки, перевірені історією цін", font=f_lead, fill=MUTED)
    d.text((92, 272), "найменша ціна за 30 днів — не та, що на ціннику", font=f_note, fill=GREEN)

    out = os.path.join(WEB, "og.png")
    im.save(out, optimize=True)
    return out


if __name__ == "__main__":
    made = [favicon(), og_card()]
    for p in made:
        print(f"  {os.path.relpath(p, ROOT)}  {os.path.getsize(p) // 1024} КБ")
    print("готово — файли комітяться, серверу Pillow не потрібен")
