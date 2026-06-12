import time
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
_memory_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")

# Token pricing (GPT-4o-mini rates)
PRICE_PER_1K_INPUT_TOKENS = 0.00015
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006

def get_user_cost(user_id: str) -> float:
    today = time.strftime("%Y-%m-%d")
    if USE_REDIS:
        try:
            key = f"budget:{user_id}:{today}"
            val = _redis.get(key)
            return float(val) if val else 0.0
        except Exception:
            pass
    
    global _memory_cost, _cost_reset_day
    if today != _cost_reset_day:
        _memory_cost = 0.0
        _cost_reset_day = today
    return _memory_cost

def check_budget(user_id: str):
    cost = get_user_cost(user_id)
    if cost >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget of ${settings.daily_budget_usd:.2f} exceeded. Try again tomorrow."
        )

def record_cost(user_id: str, input_tokens: int, output_tokens: int) -> float:
    cost = (input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
    today = time.strftime("%Y-%m-%d")
    
    if USE_REDIS:
        try:
            key = f"budget:{user_id}:{today}"
            pipe = _redis.pipeline()
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, 86400 * 2)  # Keep for 2 days
            res = pipe.execute()
            return float(res[0])
        except Exception:
            pass
            
    global _memory_cost, _cost_reset_day
    if today != _cost_reset_day:
        _memory_cost = 0.0
        _cost_reset_day = today
    _memory_cost += cost
    return _memory_cost
