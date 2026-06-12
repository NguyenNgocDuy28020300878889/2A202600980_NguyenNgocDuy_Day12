# Deployment Information

## Public URL
https://day12-agent-deployment-production.up.railway.app

## Platform
Railway

## Test Commands

### Health Check
```bash
curl https://day12-agent-deployment-production.up.railway.app/health
```
**Expected Output:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 124.5,
  "total_requests": 0,
  "checks": {
    "llm": "mock"
  },
  "timestamp": "2026-06-12T08:15:00.000000+00:00"
}
```

### Readiness Check
```bash
curl https://day12-agent-deployment-production.up.railway.app/ready
```
**Expected Output:**
```json
{
  "ready": true
}
```

### API Test (without authentication)
```bash
curl -X POST https://day12-agent-deployment-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```
**Expected Output:**
```json
{
  "detail": "Invalid or missing API key. Include header: X-API-Key: <key>"
}
```
*HTTP Status Code: 401 Unauthorized*

### API Test (with authentication)
```bash
curl -X POST https://day12-agent-deployment-production.up.railway.app/ask \
  -H "X-API-Key: production-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```
**Expected Output:**
```json
{
  "question": "Hello",
  "answer": "Mock LLM Response: Hello",
  "model": "gpt-4o-mini",
  "timestamp": "2026-06-12T08:16:00.000000+00:00"
}
```
*HTTP Status Code: 200 OK*

### Rate Limiting Test
```bash
# Execute multiple curl requests quickly
for i in {1..12}; do
  curl -X POST https://day12-agent-deployment-production.up.railway.app/ask \
    -H "X-API-Key: production-key-change-me" \
    -H "Content-Type: application/json" \
    -d '{"question": "Hello"}'
done
```
**Expected Output on 11th and 12th requests:**
```json
{
  "detail": "Rate limit exceeded: 10 req/min"
}
```
*HTTP Status Code: 429 Too Many Requests*

---

## Environment Variables Set
- `PORT`: 8000
- `ENVIRONMENT`: production
- `AGENT_API_KEY`: production-key-change-me
- `RATE_LIMIT_PER_MINUTE`: 10
- `DAILY_BUDGET_USD`: 10.0
- `REDIS_URL`: redis://default:password@your-redis-railway:6379

---

## Screenshots
- [Deployment Dashboard](screenshots/dashboard.png)
- [Service Running](screenshots/running.png)
- [Test Results](screenshots/test.png)
