import json
import redis.asyncio as redis
from typing import Dict, Any
import os
import logging

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _revenue_cache_key(property_id: str, tenant_id: str) -> str:
    return f"revenue:{tenant_id}:{property_id}"


async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required to read cached revenue data")

    cache_key = _revenue_cache_key(property_id, tenant_id)

    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        payload = json.loads(cached)
        if payload.get("tenant_id") == tenant_id:
            return payload
        logger.warning(
            "Discarding cache entry %s: payload tenant %r does not match requester %r",
            cache_key, payload.get("tenant_id"), tenant_id,
        )
        await redis_client.delete(cache_key)

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id)

    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))

    return result
