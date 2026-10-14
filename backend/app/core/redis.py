"""
QuantX — Redis Client Manager.

Provides an async Redis client for caching, pub/sub, and session storage.
Uses redis.asyncio with connection pooling.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.client import PubSub

from app.core.config import get_settings

# ── Shared pool & client (created lazily, disposed at shutdown) ──────
_pool: ConnectionPool | None = None  # type: ignore[type-arg]  # redis pool generic param unstubbed
_client: Redis | None = None  # type: ignore[type-arg]


def _build_pool() -> ConnectionPool:  # type: ignore[type-arg]  # redis pool generic param unstubbed
    """Create the Redis connection pool from settings."""
    settings = get_settings()
    return aioredis.ConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )


async def get_redis_pool() -> ConnectionPool:  # type: ignore[type-arg]  # redis pool generic param unstubbed
    """Get or create the Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = _build_pool()
    return _pool


async def get_redis_client() -> Redis:  # type: ignore[type-arg]
    """Get the shared async Redis client.

    A single client instance is reused for the whole process; it multiplexes
    over the pool, so there is no benefit to constructing one per call.

    Usage as a FastAPI dependency:
        @router.get("/cached")
        async def get_cached(redis: Redis = Depends(get_redis_client)):
            ...
    """
    global _client
    if _client is None:
        _client = aioredis.Redis(connection_pool=await get_redis_pool())
    return _client


@asynccontextmanager
async def pubsub_context(*patterns: str) -> AsyncGenerator[PubSub]:
    """Subscribe to channel patterns, guaranteeing the PubSub is released.

    A PubSub object holds its own dedicated connection out of the pool. If it
    is not closed the connection is never returned, so a pool of N connections
    is permanently exhausted after N subscribe/disconnect cycles.

    Usage:
        async with pubsub_context("market:BTCUSDT:*") as pubsub:
            async for message in pubsub.listen():
                ...
    """
    client = await get_redis_client()
    pubsub = client.pubsub()
    try:
        if patterns:
            await pubsub.psubscribe(*patterns)
        yield pubsub
    finally:
        try:
            if patterns:
                await pubsub.punsubscribe(*patterns)
        except Exception:
            pass
        await pubsub.aclose()  # type: ignore[attr-defined]  # redis-py 5.x async close, stub gap


async def close_redis() -> None:
    """Close the Redis client and connection pool.

    Should be called during application shutdown.
    """
    global _pool, _client
    if _client is not None:
        await _client.aclose()  # type: ignore[attr-defined]  # redis-py 5.x async close, stub gap
        _client = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


# Atomically increment a counter and set its TTL only on creation, so that a
# fixed window actually expires. Refreshing the TTL on every hit (INCR then
# unconditional EXPIRE) keeps the window alive for as long as traffic
# continues, which permanently locks out a caller once the limit is reached.
_INCR_WITH_TTL_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RedisManager:
    """High-level Redis operations for QuantX.

    Provides typed methods for common operations like caching,
    rate limiting, and pub/sub messaging.
    """

    def __init__(self, client: Redis) -> None:  # type: ignore[type-arg]
        self._client = client
        self._incr_script = client.register_script(_INCR_WITH_TTL_LUA)

    async def cache_set(self, key: str, value: str, ttl_seconds: int = 300) -> None:
        """Store a value in cache with TTL."""
        await self._client.setex(key, ttl_seconds, value)

    async def cache_get(self, key: str) -> str | None:
        """Retrieve a cached value, returns None if expired/missing."""
        return await self._client.get(key)

    async def cache_delete(self, key: str) -> None:
        """Remove a key from cache."""
        await self._client.delete(key)

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a Redis channel."""
        return await self._client.publish(channel, message)

    async def increment(self, key: str, ttl_seconds: int = 60) -> int:
        """Increment a fixed-window counter, setting the TTL only on creation."""
        result = await self._incr_script(keys=[key], args=[ttl_seconds])
        return int(result)

    async def is_rate_limited(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        """Check if a key has exceeded the rate limit."""
        count = await self.increment(key, window_seconds)
        return count > max_requests

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            return bool(await self._client.ping())
        except Exception:
            return False


async def get_redis_manager() -> RedisManager:
    """FastAPI dependency providing a RedisManager over the shared client."""
    return RedisManager(await get_redis_client())
