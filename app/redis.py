"""Async Redis client.

Optional infrastructure. If REDIS_URL is unset, the `redis` package is
missing, or the client can't be constructed, `redis_client` is None and
callers fall back to in-memory state. Importing this module must NEVER raise
— Redis being absent or misconfigured can't be allowed to crash app startup.
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)

redis_client = None

if settings.REDIS_URL:
    try:
        import redis.asyncio as redis

        redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    except Exception as e:
        logger.warning(
            "Redis unavailable (%s) — features that use it fall back to in-memory state",
            e,
        )
        redis_client = None
else:
    logger.info(
        "REDIS_URL not set — sync backoff state will use in-memory fallback "
        "(does not persist across restarts)"
    )


async def get_redis():
    """Dependency that provides the Redis client (may be None if unconfigured)."""
    return redis_client
