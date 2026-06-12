"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication (tách module app/auth.py)
  ✅ Rate limiting (tách module app/rate_limiter.py + Redis-backed)
  ✅ Cost guard (tách module app/cost_guard.py + Redis-backed)
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe (Redis connection check)
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
  ✅ Stateless Session (Conversation history in Redis)
"""
import os
import time
import signal
import logging
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_budget, record_cost

# Mock LLM
from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Redis Storage for Stateless Sessions
# ─────────────────────────────────────────────────────────
USE_REDIS = False
_redis = None
if settings.redis_url:
    try:
        import redis
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
        _redis.ping()
        USE_REDIS = True
        logger.info("Connected to Redis for Stateless Session Management")
    except Exception as e:
        USE_REDIS = False
        logger.warning(f"Redis not available: {e} — using in-memory store")

_memory_sessions = {}

def get_session_history(user_id: str) -> list:
    if USE_REDIS:
        try:
            val = _redis.get(f"history:{user_id}")
            return json.loads(val) if val else []
        except Exception:
            pass
    return _memory_sessions.get(user_id, [])

def save_session_history(user_id: str, history: list):
    if len(history) > 20:
        history = history[-20:]
    if USE_REDIS:
        try:
            _redis.setex(f"history:{user_id}", 3600 * 24, json.dumps(history))
            return
        except Exception:
            pass
    _memory_sessions[user_id] = history

# Context-aware mock LLM call using history
def get_contextual_answer(question: str, history: list) -> str:
    question_lower = question.lower()
    if "what is my name" in question_lower or "tên tôi là gì" in question_lower:
        for msg in reversed(history):
            if msg["role"] == "user":
                content_lower = msg["content"].lower()
                if "my name is" in content_lower:
                    name = msg["content"].split("is")[-1].strip().strip(".").strip()
                    return f"Your name is {name}."
                if "tên tôi là" in content_lower:
                    name = msg["content"].split("là")[-1].strip().strip(".").strip()
                    return f"Tên của bạn là {name}."
        return "I don't know your name yet. Please tell me your name first."
        
    if "what did i just say" in question_lower or "tôi vừa nói gì" in question_lower:
        user_msgs = [m for m in history if m["role"] == "user"]
        if len(user_msgs) >= 2:
            return f"You just said: '{user_msgs[-2]['content']}'"
        return "You haven't said anything before this."
        
    return llm_ask(question)

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    time.sleep(0.1)  # simulate init
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.pop("server", None)
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception as e:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")
    user_id: str | None = Field(None, description="Unique identifier for the user session")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }

@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    user_id = body.user_id or "default_user"
    
    # Rate limit per API key / user
    check_rate_limit(user_id)

    # Budget check
    check_budget(user_id)

    # Get conversation history from Redis/memory
    history = get_session_history(user_id)

    # Append user question to history
    history.append({"role": "user", "content": body.question})

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": user_id,
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    # Get answer (context-aware mock LLM call)
    answer = get_contextual_answer(body.question, history)

    # Append assistant answer to history
    history.append({"role": "assistant", "content": answer})
    save_session_history(user_id, history)

    # Cost tracking
    input_tokens = len(body.question.split()) * 2
    output_tokens = len(answer.split()) * 2
    record_cost(user_id, input_tokens, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    status = "ok"
    checks = {"llm": "mock" if not settings.openai_api_key else "openai"}
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if USE_REDIS:
        try:
            _redis.ping()
        except Exception:
            raise HTTPException(503, "Redis not available")
    return {"ready": True}

@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    user_id = "default_user"
    daily_cost = get_user_cost(user_id)
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(daily_cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(daily_cost / settings.daily_budget_usd * 100, 1),
    }

# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)

if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
