#!/usr/bin/env python3
"""S0.1 — probe.py: монітор поверхні крамниць + ліквідність (не конвеєр).

Валідує R-P0-3 (ліквідність) і готує дані для S0.3 (badge-rate). Стійкий до
редизайнів: рахує СИГНАЛИ (line-through стара ціна, -NN% знижка, ₴/грн, JSON-LD,
anti-bot), а не крихкі per-store CSS-селектори (§3.9 — поверхня рухлива).

Stdlib-only (urllib) — щоб запускатись у GitHub Actions без залежностей.
Продакшн-колектор (§8.3) використовує httpx; тут проба свідомо легша.

Дисципліна (бриф S0.1 / §10.9): НЕ робимо висновок з одного скану — кожна
крамниця пробується двічі підряд; розбіжність > поріг → флаг, не висновок.
Ввічливість (§10.2): один запит на хост за раз + пауза з джиттером.
Юр (§7.4): зберігаємо лише ФАКТИ (числа), не байти сторінок у репо.
"""
from __future__ import annotations
import urllib.request, urllib.error, http.cookiejar
import re, json, time, sys, os, argparse, datetime, hashlib

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 25
POLITE_DELAY = 3.0          # база паузи між запитами до ОДНОГО хоста (§10.2)
JITTER = 1.5
DIVERGENCE_PCT = 0.15       # >15% розбіжність між 2 прогонами → флаг (не висновок)

# Реальні акції-URL із §3.3 (звірка 2026-07-09). tier/cookie — очікування, probe перевіряє.
STORES = [
    {"name": "Pethouse",  "url": "https://pethouse.ua/ua/shop/koshkam/suhoi-korm/akcii/",
     "tier": "A", "cookie": False, "product_re": r'href="(/ua/[a-z0-9][a-z0-9\-/]*-\d+/?)"'},
    {"name": "PetChoice", "url": "https://petchoice.ua/discounts",
     "tier": "A", "cookie": False, "product_re": r'href="(/[a-z0-9][a-z0-9\-/]*-\d+\.html)"'},
    {"name": "MasterZoo", "url": "https://masterzoo.ua/ua/aktsii/",
     "tier": "B", "cookie": True,  "product_re": r'href="(/ua/p\d+[a-z0-9\-]*/?)"'},
    {"name": "Zootovary", "url": "https://zootovary.ua/aktsiji-t-44.html",
     "tier": "C", "cookie": False, "product_re": None},
    {"name": "Petslike",  "url": "https://petslike.ua/actions",
     "tier": "C", "cookie": False, "product_re": None},
    {"name": "Zoobonus",  "url": "https://zoobonus.ua/promo",
     "tier": "C", "cookie": False, "product_re": None},
]

# СИЛЬНІ маркери реального блоку (сторінку не віддали). NB: голий 'challenge-platform'
# і 'captcha' — НЕ блок: Cloudflare впорскує challenge-platform-скрипт на нормальні 200-сторінки
# з повним контентом (підтверджено на PetChoice/Zoobonus — хибне спрацювання). Тому окремо 'cf'.
BLOCK_MARKERS = ("just a moment", "cf_chl", "cf-chl", "cf-mitigated", "attention required",
                 "unusual traffic", "access denied", "/cdn-cgi/l/chk_", "_incapsula_", "imperva")
# NB: голі recaptcha/hcaptcha-скрипти НЕ маркер блоку — це форми на нормальній сторінці
# (хибно позначали Petslike). Реальний блок — сильні CF/Imperva-фрази вище або tiny_empty.
CF_SCRIPT = "challenge-platform"
# клас старої ціни в обох порядках: old-price / oldprice / price-old / price_old (+ line-through)
OLD_PRICE_RE = re.compile(r'class="[^"]*(?:old[\- _]?price|price[\- _]?old)[^"]*"', re.I)


def fetch(url: str, opener) -> dict:
    """Один GET. Повертає факти (статус, байти, HTML) — байти НЕ зберігаємо в репо."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "uk,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",   # без gzip: stdlib не декодує автоматично
    })
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            body = r.read()
            return {"status": r.status, "bytes": len(body),
                    "html": body.decode("utf-8", "replace"), "err": None}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "bytes": 0, "html": "", "err": f"HTTP{e.code}"}
    except Exception as e:
        return {"status": None, "bytes": 0, "html": "", "err": f"{type(e).__name__}"}


def canon_ref(path: str) -> str:
    """Канонічний external_ref із URL (§4.8): без query/utm/session, без хвостового /."""
    path = path.split("?")[0].split("#")[0].rstrip("/")
    return path.lower()


def analyze(html: str, product_re: str | None) -> dict:
    """Сигнали поверхні — стійкі до редизайну (не per-store-селектори)."""
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)   # не рахувати закоментовану розмітку
    low = html.lower()
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""
    # знижена картка: line-through (Tailwind/inline) АБО клас родини old-price/price-old
    old_price = low.count("line-through") + len(OLD_PRICE_RE.findall(html))
    # поточна ціна: ₴ + класи price-field/product-price (широко, стійко до редизайну)
    curr_price = (low.count("₴".lower())
                  + len(re.findall(r'class="[^"]*price[\- _]?field[^"]*"', low))
                  + len(re.findall(r'class="[^"]*product[\- _]?price\b[^"]*"', low)))
    discount_pct = len(re.findall(r"-\s?\d{1,2}\s?%", html))
    jsonld = low.count("application/ld+json")
    blocked = any(bm in low for bm in BLOCK_MARKERS)
    cf = CF_SCRIPT in low
    # підозра на прихований блок: крихітна сторінка без жодних цінових сигналів
    tiny_empty = len(html) < 60000 and old_price == 0 and curr_price == 0 and discount_pct == 0
    antibot = "blocked" if blocked else ("cf?" if (cf and tiny_empty) else None)
    refs = []
    if product_re:
        refs = [canon_ref(h) for h in re.findall(product_re, html)]
    uniq_refs = sorted(set(refs))
    # відбиток цін для перевірки персоналізації (#101): відсортований набір цінових токенів
    price_tokens = sorted(re.findall(r"\d[\d\s ]{2,}[,.]\d{2}", html))
    fp = hashlib.sha1("|".join(price_tokens).encode("utf-8")).hexdigest()[:12]
    return {"title": title, "old_price": old_price, "curr_price": curr_price,
            "discount_pct": discount_pct, "jsonld": jsonld, "antibot": antibot,
            "blocked": blocked, "cf": cf,
            "uniq_items": len(uniq_refs), "price_fp": fp, "n_price_tokens": len(price_tokens),
            "sample_refs": uniq_refs[:3]}


def new_opener():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def sleep_polite():
    time.sleep(POLITE_DELAY + (hash(time.time()) % 1000) / 1000 * JITTER)


def probe_store(store: dict) -> dict:
    """2 прогони підряд (анти-артефакт) + перевірка персоналізації. Лише факти."""
    runs = []
    for _ in range(2):
        op = new_opener()
        res = fetch(store["url"], op)
        if store["cookie"] and res["err"] is None:      # tier B: повторний GET із сесійною кукою
            sleep_polite()
            res = fetch(store["url"], op)
        sig = analyze(res["html"], store["product_re"]) if res["html"] else {}
        runs.append({**{k: res[k] for k in ("status", "bytes", "err")}, **sig})
        sleep_polite()

    # узгодженість 2 прогонів за ключовим числом (old_price)
    a, b = runs[0].get("old_price", 0), runs[1].get("old_price", 0)
    base = max(a, b, 1)
    consistent = abs(a - b) / base <= DIVERGENCE_PCT

    # персоналізація (#101): свіжий opener без кук vs opener з підкинутою кукою-регіоном
    op2 = new_opener()
    op2.addheaders = [("Cookie", "city=1; region=lviv; currency=UAH")]
    alt = fetch(store["url"], op2)
    alt_fp = analyze(alt["html"], store["product_re"]).get("price_fp") if alt["html"] else None
    base_fp = runs[0].get("price_fp")
    if not base_fp or not alt_fp:
        personalized = "n/a"
    else:
        personalized = "stable" if base_fp == alt_fp else "personalized"

    r0 = runs[0]
    return {
        "name": store["name"], "url": store["url"], "tier_cfg": store["tier"],
        "status": r0.get("status"), "err": r0.get("err"), "kb": round(r0.get("bytes", 0) / 1024),
        "title": r0.get("title", ""), "antibot": r0.get("antibot"),
        "blocked": r0.get("blocked", False), "cf": r0.get("cf", False),
        "curr_price": r0.get("curr_price", 0), "old_price": r0.get("old_price", 0),
        "discount_pct": r0.get("discount_pct", 0), "jsonld": r0.get("jsonld", 0),
        "uniq_items": r0.get("uniq_items", 0), "sample_refs": r0.get("sample_refs", []),
        "run2_old_price": b, "consistent": consistent,
        "personalization": personalized,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="лише крамниці, чиї імена містять цей підрядок")
    ap.add_argument("--out", default="probe_results", help="тека результатів (JSONL, комітиться)")
    args = ap.parse_args()

    stores = [s for s in STORES if not args.only or args.only.lower() in s["name"].lower()]
    ts = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    rows = []
    for s in stores:
        row = probe_store(s)
        row["probed_at"] = ts
        rows.append(row)
        flag = "" if row["consistent"] else "  ⚠НЕУЗГОДЖЕНО(2 прогони)"
        ab = f"  antibot={row['antibot']}" if row["antibot"] else ""
        print(f"{row['name']:10} HTTP={row['status']} {row['kb']:>5}КБ  "
              f"curr={row['curr_price']:>3} old={row['old_price']:>3} "
              f"-%={row['discount_pct']:>3} jsonld={row['jsonld']} "
              f"uniq={row['uniq_items']:>3}  perso={row['personalization']}{ab}{flag}")

    os.makedirs(args.out, exist_ok=True)
    day = ts[:10]
    path = os.path.join(args.out, f"probe-{day}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n→ {len(rows)} рядків додано у {path}")


if __name__ == "__main__":
    main()
