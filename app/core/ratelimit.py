"""In-process sliding-window rate limiter + ASGI middleware.

Sufficient for a single-process demo deployment; note in production multi-
worker setups you would move this to a shared store (Redis). Kept dependency-
free and honest about that limitation.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .errors import error_envelope


class SlidingWindowRateLimiter:
    """Tracks request timestamps per key and allows at most `limit` per minute."""

    def __init__(self, limit_per_minute: int = 120) -> None:
        self.limit = max(1, int(limit_per_minute))
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        window = 60.0
        async with self._lock:
            hits = self._hits[key]
            # Drop events older than the window.
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = int(window - (now - hits[0])) + 1
                return False, retry_after
            hits.append(now)
            # Opportunistic cleanup for inactive keys to bound memory.
            if len(self._hits) > 10_000:
                self._hits = defaultdict(deque)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Keyed by client IP (honouring X-Forwarded-For when trusted)."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limit_per_minute: int = 120,
        trusted_proxy_headers: bool = False,
    ) -> None:
        super().__init__(app)
        self.limiter = SlidingWindowRateLimiter(limit_per_minute)
        self.trusted_proxy_headers = trusted_proxy_headers

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        if self.trusted_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                ip = forwarded.split(",")[0].strip() or ip
        allowed, retry_after = await self.limiter.check(ip)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=error_envelope(
                    "rate_limited",
                    f"Too many requests. Retry in {retry_after}s.",
                ),
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
