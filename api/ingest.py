"""Distributed ingest (S10): довірені колектори шлють зібране на сервер.

Навіщо: наш ДЦ-IP (Hetzner) отримує 403 від Rozetka/Allo/Foxtrot/Moyo/... Довірені
колектори (оператор + друзі) збирають зі СВОЇХ резидентних мереж, зі згодою, і шлють
сюди. Це НЕ botnet: збирають ВЛАСНИКИ проекту, не несвідомі клієнти (§7.4/§7.7).

Два тверді правила (без них ingest = дірка в єдиному активі — базі):
  1. Автентифікація per-колектор — лише відомі bearer-токени (`INGEST_TOKENS`). Свій
     токен на кожного → витік одного відкликається окремо.
  2. Сервер ВАЛІДУЄ кожен елемент, не вірить на слово. Довіра до людини ≠ довіра до
     кожного байта (телефон можна зламати; база — єдиний актив). URL мусить бути на
     домені крамниці, ціна — у розумному діапазоні, назва — не порожня.
"""
from __future__ import annotations

import hmac
import os
from urllib.parse import urlsplit

from adapters.base import RawItem, canon_ref
from db.store import load_categories, persist_items, upsert_source

# ── Сервер — АВТОРИТЕТ, хто може бути джерелом і які хости валідні ────────────────
# Колектор не може «вигадати» джерело: лише ці назви приймаються, і URL кожного
# елемента мусить бути на дозволеному хості (проти інʼєкції чужих/фішинг-URL).
INGEST_SOURCES: dict[str, dict] = {
    "Foxtrot":  {"base_url": "https://www.foxtrot.com.ua", "hosts": ("foxtrot.com.ua",)},
    "Moyo":     {"base_url": "https://www.moyo.ua",        "hosts": ("moyo.ua",)},
    "Eldorado": {"base_url": "https://eldorado.ua",        "hosts": ("eldorado.ua",)},
    "Rozetka":  {"base_url": "https://rozetka.com.ua",     "hosts": ("rozetka.com.ua",)},
    "Allo":     {"base_url": "https://allo.ua",            "hosts": ("allo.ua",)},
}

PRICE_MIN_KOP = 100                 # 1 грн — нижче майже напевно помилка парсингу
PRICE_MAX_KOP = 100_000_000         # 1 000 000 грн — стеля здорового глузду
_MAX_TITLE = 300
_MAX_REF = 500
_MAX_URL = 600


def load_tokens() -> dict[str, str]:
    """token → label з env `INGEST_TOKENS` (формат: `label:token,label2:token2`).

    Токен генерувати `openssl rand -hex 32`; класти в /etc/hapay/hapay.env, НЕ в git.
    """
    raw = os.environ.get("INGEST_TOKENS", "").strip()
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        label, tok = pair.split(":", 1)
        label, tok = label.strip(), tok.strip()
        if label and tok:
            out[tok] = label
    return out


def collector_label(authorization: str | None) -> str | None:
    """Повертає label колектора для валідного `Authorization: Bearer <token>`, інакше None.
    Порівняння — constant-time (hmac.compare_digest) проти timing-атак."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    for known, label in load_tokens().items():
        if hmac.compare_digest(token, known):
            return label
    return None


def _host_ok(url: str, allowed: tuple[str, ...]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == a or host.endswith("." + a) for a in allowed)


def validate_item(source: str, raw: dict) -> tuple[RawItem | None, str | None]:
    """Один елемент від колектора → (RawItem, None) або (None, причина-відмови).

    Сервер НЕ вірить на слово навіть довіреному колектору: усе перевіряється тут.
    """
    hosts = INGEST_SOURCES[source]["hosts"]

    url = raw.get("url")
    if not isinstance(url, str) or not (0 < len(url) <= _MAX_URL):
        return None, "url: порожній/задовгий"
    if urlsplit(url).scheme != "https":
        return None, "url: лише https"
    if not _host_ok(url, hosts):
        return None, f"url не на домені {source} ({hosts})"

    title = raw.get("title")
    if not isinstance(title, str) or not (0 < len(title.strip()) <= _MAX_TITLE):
        return None, "title: порожній/задовгий"

    now = raw.get("price_now_kop")
    if not isinstance(now, int) or isinstance(now, bool) or not (PRICE_MIN_KOP <= now <= PRICE_MAX_KOP):
        return None, f"price_now_kop поза [{PRICE_MIN_KOP},{PRICE_MAX_KOP}]"

    old = raw.get("price_old_kop")
    if old is not None:
        if not isinstance(old, int) or isinstance(old, bool) or not (PRICE_MIN_KOP <= old <= PRICE_MAX_KOP):
            return None, "price_old_kop поза діапазоном"
        if old <= now:
            old = None                                  # «стара» не вища за поточну — не знижка

    ext = raw.get("external_ref")
    if not isinstance(ext, str) or not (0 < len(ext) <= _MAX_REF):
        return None, "external_ref: порожній/задовгий"

    img = raw.get("image_url")
    if img is not None:
        if not isinstance(img, str) or len(img) > _MAX_URL or urlsplit(img).scheme != "https":
            img = None                                  # погане фото не валить елемент — просто нема

    variant = raw.get("variant_note")
    if variant is not None and (not isinstance(variant, str) or len(variant) > 120):
        variant = None

    in_stock = raw.get("in_stock", True)
    if not isinstance(in_stock, bool):
        in_stock = True

    return RawItem(
        external_ref=canon_ref(ext),
        url=url,
        title=title.strip(),
        price_now_kop=now,
        price_old_kop=old,
        in_stock=in_stock,
        image_url=img,
        variant_note=variant,
    ), None


def ingest_batch(conn, source: str, items: list) -> dict:
    """Валідує й персистить батч від колектора. Погані елементи ВІДКИДАЄ (не валить добрі).

    `scan_run` — песимістично 'failed'→'ok' (T13). `source_method='satellite'` фіксує
    провенанс: ці снапшоти прийшли не з нашого прямого збору.
    """
    if source not in INGEST_SOURCES:
        raise ValueError(f"невідоме джерело: {source!r}")
    if not isinstance(items, list):
        raise ValueError("items має бути списком")

    valid: list[RawItem] = []
    seen: set[str] = set()
    rejected: list[str] = []
    for raw in items[:5000]:                            # стеля батчу — проти зловмисного роздування
        if not isinstance(raw, dict):
            rejected.append("не-обʼєкт"); continue
        item, why = validate_item(source, raw)
        if item is None:
            rejected.append(why or "?"); continue
        if item.external_ref in seen:                   # дедуп у межах батчу
            continue
        seen.add(item.external_ref)
        valid.append(item)

    base_url = INGEST_SOURCES[source]["base_url"]
    source_id = upsert_source(conn, source, base_url, adapter_kind="ssr",
                              platform="custom", fetch_tier="A")
    scan_run_id = conn.execute(
        "INSERT INTO scan_run (source_id, surface, status) VALUES (%s,'discovery','failed') "
        "RETURNING scan_run_id", (source_id,)).fetchone()[0]

    categories = load_categories(conn)
    n = persist_items(conn, source_id, valid, categories,
                      source_method="satellite", scan_run_id=scan_run_id)

    status = "ok" if valid and not rejected else ("partial" if valid else "failed")
    conn.execute("UPDATE scan_run SET finished_at = now(), items_seen = %s, status = %s "
                 "WHERE scan_run_id = %s", (n, status, scan_run_id))

    # унікальні причини відмов (без спаму) — щоб колектор бачив, що відкинуто й чому
    reasons: dict[str, int] = {}
    for r in rejected:
        reasons[r] = reasons.get(r, 0) + 1
    return {"source": source, "accepted": n, "rejected": len(rejected),
            "reasons": reasons, "status": status}
