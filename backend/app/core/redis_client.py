from redis.asyncio import Redis
from app.core.config import settings

redis: Redis | None = None

async def get_redis() -> Redis:
    global redis
    if redis is None:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return redis