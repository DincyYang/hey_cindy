# cloud/state.py
"""Light state lives in Redis (hot, frequently-read, shared across processes).

If Redis is unavailable we degrade to an in-process value so the API keeps
working — the light still toggles, we just lose cross-process sharing and
persistence until Redis is back. The core "set the light" path must never 500
because the cache is down.
"""
import os
import logging

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_KEY = "hey_cindy:light"


class LightState:
    def __init__(self, client: "redis.Redis | None" = None):
        # from_url is lazy — it does not connect until the first command,
        # so constructing this never fails even if Redis is down.
        self._client = client or redis.Redis.from_url(REDIS_URL, decode_responses=True)
        self._fallback = "off"  # in-process degraded store

    def get(self) -> str:
        try:
            value = self._client.get(_KEY)
            return value if value is not None else self._fallback
        except redis.RedisError as e:
            logger.warning("Redis read failed (%s); using in-memory fallback", e)
            return self._fallback

    def set(self, value: str) -> None:
        self._fallback = value  # always keep the local copy current
        try:
            self._client.set(_KEY, value)
        except redis.RedisError as e:
            logger.warning("Redis write failed (%s); kept in-memory only", e)
