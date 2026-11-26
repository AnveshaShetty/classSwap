import math
import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse


GLOBAL_REQUEST_LIMIT = 300
PUBLIC_REQUEST_LIMIT = 120
LOGIN_REQUEST_LIMIT = 30
RESET_REQUEST_LIMIT = 10
UPLOAD_REQUEST_LIMIT = 10
GLOBAL_WINDOW_SECONDS = 60
RESET_WINDOW_SECONDS = 15 * 60

PUBLIC_PATHS = {
    "/",
    "/login",
    "/reset-password",
    "/health",
    "/auth/login",
    "/auth/password-reset/request",
    "/auth/password-reset/confirm",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
}


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def _bound_keys(self) -> None:
        if len(self._requests) < 10_000:
            return
        now = time.monotonic()
        for key, requests in list(self._requests.items()):
            while requests and requests[0] <= now - RESET_WINDOW_SECONDS:
                requests.popleft()
            if not requests:
                del self._requests[key]
            if len(self._requests) < 8_000:
                return
        if len(self._requests) >= 10_000:
            self._requests.pop(next(iter(self._requests)))

    def retry_after(
        self,
        client_ip: str,
        category: str,
        limit: int,
        window_seconds: int,
    ) -> int | None:
        now = time.monotonic()
        key = (client_ip, category)
        with self._lock:
            if key not in self._requests:
                self._bound_keys()
            requests = self._requests[key]
            cutoff = now - window_seconds
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= limit:
                return max(1, math.ceil(requests[0] + window_seconds - now))
            requests.append(now)
        return None

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()


rate_limiter = InMemoryRateLimiter()


def rate_limit_response(request: Request) -> JSONResponse | None:
    client_ip = request.client.host if request.client is not None else "unknown"
    policies = [
        ("global", GLOBAL_REQUEST_LIMIT, GLOBAL_WINDOW_SECONDS),
    ]
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static/"):
        policies.append(("public", PUBLIC_REQUEST_LIMIT, GLOBAL_WINDOW_SECONDS))
    if path == "/auth/login":
        policies.append(("login", LOGIN_REQUEST_LIMIT, GLOBAL_WINDOW_SECONDS))
    elif path.startswith("/auth/password-reset/"):
        policies.append(("password-reset", RESET_REQUEST_LIMIT, RESET_WINDOW_SECONDS))
    elif path == "/timetable/import":
        policies.append(("timetable-upload", UPLOAD_REQUEST_LIMIT, GLOBAL_WINDOW_SECONDS))

    for category, limit, window in policies:
        retry_after = rate_limiter.retry_after(client_ip, category, limit, window)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )
    return None
