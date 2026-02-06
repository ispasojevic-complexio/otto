"""Redis-based distributed rate limiter (token bucket per domain)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from redis.asyncio import Redis

# Lua script: if key has no TTL or expired, set to 1 and return 1 (allowed).
# Else increment; if over limit, return 0 (deny). Otherwise return 1.
# We use a simple sliding-window style: key = rate_limit:{domain}, value = count,
# TTL = 1 second. Each second we allow rate_limit_per_second requests.
# Alternative: token bucket with last_refill and tokens stored in Redis.
# Simpler approach: key = rate_limit:{domain}, type = string with last request timestamp.
# Allow if now - last >= 1/rate. Set last = now.
# Lua: GET key; if nil or (now - tonumber(val)) >= 1/rate then SET key now EX 2 return 1 else return 0
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local min_interval = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local last = redis.call('GET', key)
if last == false then
  redis.call('SET', key, now, 'EX', ttl)
  return 1
end
last = tonumber(last)
if now - last >= min_interval then
  redis.call('SET', key, now, 'EX', ttl)
  return 1
end
return 0
"""


class RateLimiter:
    """Per-domain rate limiter using Redis. Blocks until a token is available."""

    def __init__(
        self,
        redis_url: str,
        requests_per_second: float = 1.0,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self._client: Any = Redis.from_url(redis_url, decode_responses=True)
        self._min_interval = (
            1.0 / requests_per_second if requests_per_second > 0 else 0.0
        )
        self._poll_interval = poll_interval_seconds
        self._ttl = max(2, int(self._min_interval) + 1)
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        if self._script_sha is None:
            self._script_sha = await self._client.script_load(RATE_LIMIT_SCRIPT)
        return self._script_sha

    async def acquire(self, domain: str) -> None:
        """Block until a request is allowed for this domain."""
        key = f"rate_limit:{domain}"
        while True:
            sha = await self._ensure_script()
            now = time.time()  # wall clock so multiple instances agree
            result = await self._client.evalsha(
                sha,
                1,
                key,
                str(now),
                str(self._min_interval),
                str(self._ttl),
            )
            if result == 1:
                return
            await asyncio.sleep(self._poll_interval)
