"""Надсилання транзакційних листів (S13) — stdlib smtplib, без зовнішніх пакетів.

Канал через env (працює з SES/Brevo/будь-яким SMTP-релеєм):
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_TLS (default "1").

БЕЗ SMTP_HOST → LogSender: код падає в journal сервера (dev / канал ще не підключено).
Той самий принцип, що alert_collect: фіча працює вже сьогодні, реальний канал = лише
env, без зміни коду. `send` НІКОЛИ не кидає — збій листа не має валити реєстрацію
(користувач перезапросить код; логіка акаунта не заручник пошти).

⚠ Deliverability (щоб листи не в спам) вимагає SPF/DKIM/DMARC на домені FROM — це
робота в DNS, не в коді (🧭 оператор).
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage


def _smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def send(to: str, subject: str, body: str) -> bool:
    """Надіслати текстовий лист. True — прийнято релеєм; False — не надіслано (немає
    каналу або збій). Ніколи не кидає."""
    if not _smtp_configured():
        # LogSender: код у журналі сервера — розробка/канал ще не підключено.
        print(f"[email:LOG] до={to} тема={subject!r}\n{body}", file=sys.stderr)
        return False
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    pw = os.environ.get("SMTP_PASS", "")
    sender = os.environ.get("SMTP_FROM", user)
    # Порт 465 — неявний SSL (SMTP_SSL); 587/2525 — STARTTLS. SendPulse дає всі три;
    # автовибір за портом прибирає найтиповішу плутанину налаштування.
    use_ssl = os.environ.get("SMTP_SSL", "1" if port == 465 else "0") != "0"
    use_starttls = not use_ssl and os.environ.get("SMTP_TLS", "1") != "0"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with cls(host, port, timeout=20) as s:
            if use_starttls:
                s.starttls()
            if user:
                s.login(user, pw)
            s.send_message(msg)
        return True
    except Exception as e:                       # мережа/авторизація/релей — не валимо потік
        print(f"[email] збій надсилання до {to}: {type(e).__name__}: {e}", file=sys.stderr)
        return False


# ── тексти листів (фактологічні, українською; бренд «Хапай») ──────────────────────
def verify_body(code: str) -> tuple[str, str]:
    return ("Хапай — підтвердження email",
            f"Твій код підтвердження: {code}\n\n"
            "Введи його в застосунку, щоб підтвердити email. Код діє 24 години.\n"
            "Якщо ти не реєструвався в Хапай — просто зігноруй цей лист.")


def reset_body(code: str) -> tuple[str, str]:
    return ("Хапай — скидання пароля",
            f"Код для зміни пароля: {code}\n\n"
            "Введи його в застосунку разом із новим паролем. Код діє 1 годину.\n"
            "Якщо ти не просив зміну пароля — зігноруй цей лист, пароль лишиться тим самим.")


def signup_attempt_body() -> tuple[str, str]:
    """Лист власнику адреси, коли за нею СПРОБУВАЛИ зареєструватись, а акаунт уже є.

    Дві причини, і друга не менш важлива за першу:
    1. людині корисно знати, що хтось вводив її адресу;
    2. лист іде В ОБОХ випадках (нова адреса й наявна), інакше витік просто переїхав
       би з коду відповіді в ЧАС: відправка SMTP довша за її відсутність, і «чи є
       акаунт» знову читалося б із таймінгу (рівно так ми вже обпеклись на login).

    Коду тут НЕМА: якби спроба реєстрації надсилала власнику дійсний код, чужа людина
    керувала б чужою поштою — це був би не захист, а вектор.
    """
    return ("Хапай — спроба реєстрації з вашою адресою",
            "Хтось намагався створити акаунт Хапай із цією адресою, але вона вже "
            "зареєстрована.\n\n"
            "Якщо це ви — просто увійдіть звичайним паролем; якщо забули його, "
            "скористайтесь відновленням пароля.\n"
            "Якщо це не ви — нічого робити не треба: акаунт не змінився, і доступу "
            "до нього ніхто не отримав.")


def price_drop_body(items: list[dict], unsub: str) -> tuple[str, str]:
    """Лист «ціна впала». Це НЕ транзакційний лист: його шлемо ми, з власної
    ініціативи, тож він мусить нести дві речі, яких транзакційні не мають —
    привід («ви просили стежити») і вихід (посилання «не писати»).

    Формулювання те саме, що в інтерфейсі: ми не кажемо «знижка», ми кажемо, що
    ЦІНА ЗНИЗИЛАСЬ за нашими вимірами. Різниця не косметична: знижку оголошує
    крамниця, а зниження бачимо ми."""
    n = len(items)
    word = "товар" if n % 10 == 1 and n % 100 != 11 else (
        "товари" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "товарів")
    subject = (f"Подешевшав {items[0]['title'][:40]}" if n == 1
               else f"Подешевшало {n} {word} з ваших відстежень")

    lines = ["Ви просили стежити за цінами — ось що змінилось за нашими вимірами.", ""]
    for it in items:
        price = f"{it['current_kop'] // 100} грн"
        was = it.get("baseline_kop") or it.get("was_kop")
        was_s = f" (було {was // 100} грн)" if was else ""
        tgt = it.get("target_kop")
        goal = f" — ваша ціль {tgt // 100} грн" if tgt else ""
        lines.append(f"• {it['title'][:70]}")
        lines.append(f"  {price}{was_s}{goal} · {it.get('store', '')}")
        lines.append(f"  https://hapay.today/product/{it['store_product_id']}")
        lines.append("")
    lines += [
        "Ціни й назви — публічні дані крамниць; зниження рахуємо з нашої власної",
        "історії спостережень. Перевірте в крамниці перед покупкою: ми бачимо ціну",
        "на сторінці, а не пакування.",
        "",
        f"Не писати більше про ціни: {unsub}",
    ]
    return subject, "\n".join(lines)
