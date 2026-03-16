# PRD: Challenge 01 — Session Memory with Azure Cache for Redis

## Product Requirement

Replace the in-memory session storage in `backend/server.py` with Azure Cache for Redis so that chat sessions persist across backend restarts and scale across instances.

## Current State (Before)

The `SessionManager` class in `backend/server.py` uses plain Python dictionaries:
- `_sessions: dict[str, AgentSession]` — live session objects
- `_session_metadata: dict[str, dict]` — title, created_at, last_activity, user_id
- `_message_counts: dict[str, int]` — turn counters

All data is lost when the process restarts. The class methods are synchronous.

## Target State (After)

The `SessionManager` class uses `redis.asyncio.Redis` as the persistence layer:
- `_sessions` remains as an in-memory hot cache for live `AgentSession` Python objects
- `_session_metadata` and `_message_counts` dicts serve as **fallback** when Redis is not connected
- When Redis IS connected, all durable state goes to Redis instead of dicts

### Redis Key Schema

| Key | Redis Type | Value |
|-----|-----------|-------|
| `session:{session_id}:state` | STRING | JSON from `AgentSession.to_dict()` — full conversation history |
| `session:{session_id}:metadata` | HASH | Fields: `title`, `created_at`, `last_activity`, `user_id` |
| `session:{session_id}:message_count` | STRING | Integer counter, updated via `INCRBY` |

### Graceful Degradation

The `connect()` method must:
1. Check if `REDIS_HOST` env var is set — if not, log a warning and stay in-memory mode
2. If set, attempt to connect and `PING` — if that fails, log a warning and stay in-memory mode
3. Only set `self._redis` to a live client on successful connection

Every method checks `if self._redis is not None:` to decide Redis vs in-memory path.

## Environment Variables

| Variable | Example | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `redis-mhaimemk001.redis.cache.windows.net` | Redis hostname (empty = in-memory mode) |
| `REDIS_PORT` | `6380` | Redis port (6380 for TLS) |
| `REDIS_PASSWORD` | `<access-key>` | Primary access key |
| `REDIS_SSL` | `true` | Enable TLS |

## Dependencies

Add to `backend/pyproject.toml`:
```
"redis>=5.0.0"
```

## API Changes

**No external API changes.** All existing endpoints (`/sessions`, `/chat`, etc.) work identically. The only change is internal — `SessionManager` methods become `async`.

### Call Site Updates Required

These `SessionManager` methods change from sync to async and all callers must add `await`:
- `create_session()` — called in `POST /sessions`, `POST /chat`
- `get_session()` — called in `GET /sessions/{id}/history`, `POST /chat`
- `delete_session()` — called in `DELETE /sessions/{id}`
- `update_session()` — called in `PUT /sessions/{id}`
- `save_session_state()` — called in `stream_agent_response()`
- `increment_message_count()` — called in `stream_agent_response()`

The helper `_assert_session_owner()` must also become `async` since it queries session metadata.

## FastAPI Lifespan Integration

In the `lifespan()` function:
- **Startup:** call `await session_manager.connect()`
- **Shutdown:** call `await session_manager.close()`

## File Changes Summary

| File | Change |
|------|--------|
| `backend/pyproject.toml` | Add `redis>=5.0.0` dependency |
| `backend/.env` | Add `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_SSL` |
| `backend/server.py` | Rewrite `SessionManager`, update all call sites to async, update lifespan |
| `infra/modules/user_seat/main.tf` | Add Redis env vars + secret to backend Container App |

## Verification

1. **Without Redis (before):** Remove or leave `REDIS_HOST` empty in `.env`. Backend starts and works in-memory. Logs show: `"REDIS_HOST not set — session manager running in-memory only"`
2. **With Redis (after):** Set `REDIS_HOST` and credentials. Backend starts and connects. Logs show: `"Redis connected: <host>:6380 (ssl=True)"`. Use `redis-cli` to verify keys exist after chatting.
3. **Restart test:** With Redis connected, restart backend. Resume a previous session — messages should be preserved.

## Acceptance Criteria

- [ ] Backend works in-memory when `REDIS_HOST` is not set (no crash)
- [ ] Backend connects to Redis when `REDIS_HOST` is set and reachable
- [ ] Backend falls back to in-memory with a warning when Redis is unreachable
- [ ] Chat sessions create `session:*:state`, `session:*:metadata`, `session:*:message_count` keys in Redis
- [ ] Sessions survive backend restarts when Redis is connected
- [ ] All existing API endpoints continue to work without changes
