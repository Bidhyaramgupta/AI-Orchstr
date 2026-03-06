from __future__ import annotations
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException
from redis.asyncio import Redis

_LUA = (Path(__file__).with_name("token_bucket.lua")).read_text()


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: float
    retry_after_ms: int


def now_ms() -> int:
    return int(time.time() * 1000)


def bucket_key(user_key: str, provider: str, model: str, kind: str) -> str:
    return f"rl:{kind}:{user_key}:{provider}:{model}"


async def reserve(
    redis: Redis,
    *,
    user_key: str,
    provider: str,
    model: str,
    kind: str,
    capacity: float,
    refill_per_sec: float,
    cost: float,
) -> RateLimitResult:
    if capacity <= 0:
        return RateLimitResult(True, remaining=capacity, retry_after_ms=0)

    refill_per_ms = refill_per_sec / 1000.0
    key = bucket_key(user_key, provider, model, kind)

    res = await redis.eval(
        _LUA,
        1,
        key,
        now_ms(),
        capacity,
        refill_per_ms,
        cost,
    )

    allowed = int(res[0]) == 1
    remaining = float(res[1])
    retry_after_ms = int(res[2])

    return RateLimitResult(
        allowed=allowed,
        remaining=remaining,
        retry_after_ms=retry_after_ms,
    )


def raise_429(result: RateLimitResult, kind: str) -> None:
    retry_after_s = max(1, (result.retry_after_ms + 999) // 1000)
    raise HTTPException(
        status_code=429,
        detail=f"Rate limit exceeded ({kind}). Retry after {retry_after_s}s.",
        headers={"Retry-After": str(retry_after_s)},
    )