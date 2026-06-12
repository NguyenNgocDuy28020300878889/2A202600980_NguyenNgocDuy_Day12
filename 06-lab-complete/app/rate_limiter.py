import time
from collections import defaultdict, deque
from fastapi import HTTPException
import redis
from app.config import settings

# Initialize Redis client
USE_REDIS = False
_redis = None
if settings.redis_url:
    try:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
        _redis.ping()
        USE_REDIS = True
    except Exception:
        USE_REDIS = False

# In-memory fallback structures
_rate_windows = defaultdict(deque)

def check_rate_limit(user_id: str):
    now = time.time()
    limit = settings.rate_limit_per_minute
    
    if USE_REDIS:
        try:
            key = f"rate_limit:{user_id}"
            pipe = _redis.pipeline()
            # Remove keys older than 60 seconds
            pipe.zremrangebyscore(key, 0, now - 60)
            # Count elements in the set
            pipe.zcard(key)
            # Run pipeline
            _, count = pipe.execute()
            
            if count >= limit:
                oldest_list = _redis.zrange(key, 0, 0, withscores=True)
                retry_after = 60
                if oldest_list:
                    # In newer redis-py versions, zrange might return just members or (member, score) depending on parameters.
                    # Let's extract the timestamp score safely.
                    try:
                        oldest_ts = float(oldest_list[0])
                    except ValueError:
                        oldest_ts = float(oldest_list[0][1])
                    retry_after = max(1, int(oldest_ts + 60 - now) + 1)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {limit} req/min",
                    headers={"Retry-After": str(retry_after)},
                )
            
            # Add current request timestamp
            pipe = _redis.pipeline()
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, 60)
            pipe.execute()
            return
        except HTTPException:
            raise
        except Exception:
            pass

    # In-memory sliding window fallback
    window = _rate_windows[user_id]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= limit:
        retry_after = max(1, int(window[0] + 60 - now) + 1)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit} req/min",
            headers={"Retry-After": str(retry_after)},
        )
    window.append(now)
