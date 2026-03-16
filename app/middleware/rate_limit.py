"""
Simple in-memory rate limiter for auth endpoints.

Tracks request counts per IP address using a sliding window.
No external dependencies required.
"""
import time
from collections import defaultdict
from fastapi import HTTPException, Request, status


# {ip: [(timestamp, ...), ...]}
_request_log: dict[str, list[float]] = defaultdict(list)


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For from proxies."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(max_requests: int = 10, window_seconds: int = 60):
    """
    Returns a FastAPI dependency that enforces a sliding-window rate limit.

    Args:
        max_requests: Maximum allowed requests per window.
        window_seconds: Length of the sliding window in seconds.
    """
    async def _check(request: Request):
        ip = _get_client_ip(request)
        now = time.monotonic()
        cutoff = now - window_seconds

        # Prune old entries
        log = _request_log[ip]
        _request_log[ip] = [t for t in log if t > cutoff]

        if len(_request_log[ip]) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please wait before trying again.",
                headers={"Retry-After": str(window_seconds)},
            )

        _request_log[ip].append(now)

    return _check
