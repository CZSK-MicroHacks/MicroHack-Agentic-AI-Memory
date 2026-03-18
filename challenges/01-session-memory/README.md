# Challenge 01 — Session Memory (Azure Cache for Redis)

## Goal

Replace the **in-memory session storage** in the backend with **Azure Cache for Redis** so that conversation sessions survive process restarts.

Currently, the `SessionManager` class in `backend/server.py` stores everything in plain Python dictionaries — when the backend restarts, **all sessions are lost**. Your task is to back it with Redis.

## Prerequisites

- Azure Cache for Redis is already deployed (Basic SKU, TLS-only on port 6380)
- Get the hostname and access key from the Azure Portal → your Redis resource → **Access keys**

## How to Implement

📋 **Use the PRD document** — open [`challenges/01-session-memory/PRD.md`](PRD.md) in your editor. It contains the full specification: Redis key schema, env vars, method-by-method changes, and acceptance criteria.

> **Tip:** With the PRD open, use GitHub Copilot to help implement the changes. Copilot will pick up the PRD as context and generate code that matches the spec.

## Quick Steps

1. Add `redis>=5.0.0` to `backend/pyproject.toml` → run `uv sync`
2. Add `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_SSL` to `backend/.env`
3. Rewrite `SessionManager` in `backend/server.py` to use `redis.asyncio` (see PRD for details)
4. Add `await session_manager.connect()` / `.close()` in the FastAPI `lifespan()`
5. Update all call sites (methods changed from sync → async)

## Verify

```bash
# Start backend
uv run uvicorn server:app --reload

# Chat via the frontend, then check Redis:
redis-cli -h <your-redis-host> -p 6380 --tls -a <your-access-key>
> KEYS session:*
> HGETALL session:<some-id>:metadata
```

## Success Criteria

- [ ] Backend starts and connects to Redis (or falls back to in-memory if Redis is unavailable)
- [ ] Chat sessions work normally
- [ ] Redis contains `session:*:state`, `session:*:metadata`, `session:*:message_count` keys
- [ ] After restarting the backend, existing sessions resume from Redis

