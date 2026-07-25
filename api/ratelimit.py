"""In-memory rate limiter (stdlib) для дорогих auth-ендпойнтів (bug-review 2026-07-25).

Sliding-window per-IP. uvicorn — 1 воркер (systemd ExecStart без --workers), тож стан
спільний для всіх запитів. Захищає:
  · /api/auth/login    — brute-force паролів + CPU-DoS (кожна спроба палить pbkdf2 600k);
  · /api/auth/register — масове створення акаунтів.

IP беремо з `X-Real-IP` (його ставить Caddy з РЕАЛЬНОГО remote_host; сервер слухає лише
127.0.0.1 за Caddy, тож заголовок приходить від Caddy, не від клієнта — підробити не можна).
Sync-ендпойнти FastAPI йдуть у threadpool (кілька потоків) → стан під Lock.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_MAX_WINDOW_S = 3600          # найдовше вікно (register) — орієнтир для чистки
_SWEEP_EVERY_S = 60           # як часто прибирати застарілі ключі (проти росту пам'яті)


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def check(self, key: str, limit: int, window_s: int, now: float | None = None) -> tuple[bool, int]:
        """(allowed, retry_after_s). Спробу реєструємо ЛИШЕ якщо allowed — відхилені
        не подовжують блок (інакше зловмисник тримав би вікно повним нескінченно)."""
        now = time.time() if now is None else now
        cutoff = now - window_s
        with self._lock:
            if now - self._last_sweep > _SWEEP_EVERY_S:
                self._sweep(now)
                self._last_sweep = now
            dq = self._hits[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= limit:
                retry = int(dq[0] + window_s - now) + 1
                if not dq:                       # ключ став порожнім — не тримаємо
                    self._hits.pop(key, None)
                return False, max(retry, 1)
            dq.append(now)
            return True, 0

    def _sweep(self, now: float) -> None:
        """Прибрати ключі без активності за найдовше вікно (пам'ять не росте від
        разових IP). Викликається під Lock."""
        stale = [k for k, dq in self._hits.items()
                 if not dq or dq[-1] <= now - _MAX_WINDOW_S]
        for k in stale:
            self._hits.pop(k, None)


def client_ip(request) -> str:
    """Реальний IP клієнта. X-Real-IP (Caddy, довірений) → X-Forwarded-For (перший) →
    прямий peer. Порожній рядок неможливий — є хоча б '?'."""
    xr = request.headers.get("x-real-ip")
    if xr and xr.strip():
        return xr.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff and xff.strip():
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


# Спільні інстанси (стан у процесі). Ліміти консервативні: легітимному входу вистачає,
# автоматичному перебору — ні.
login_limiter = RateLimiter()
register_limiter = RateLimiter()
email_limiter = RateLimiter()                # надсилання (resend/reset-request) — дороге
code_limiter = RateLimiter()                 # перебір коду (verify/reset-confirm) — brute-force

LOGIN_LIMIT, LOGIN_WINDOW_S = 10, 300        # 10 спроб / 5 хв / IP
REGISTER_LIMIT, REGISTER_WINDOW_S = 5, 3600  # 5 реєстрацій / год / IP
EMAIL_LIMIT, EMAIL_WINDOW_S = 5, 3600        # 5 листів / год / IP (проти mail-bombing)
CODE_LIMIT, CODE_WINDOW_S = 10, 600          # 10 спроб коду / 10 хв / IP (проти перебору)
