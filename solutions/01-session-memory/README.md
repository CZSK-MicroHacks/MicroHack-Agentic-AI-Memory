# Solution 01 — Session Memory (Azure Cache for Redis)

## Summary

This solution replaces the in-memory `SessionManager` with a Redis-backed implementation.  Live `AgentSession` objects stay in a Python dict as a hot cache, while all durable state is persisted to Azure Cache for Redis.

## Changes Made

### 1. `backend/pyproject.toml`
Added `redis>=5.0.0` to dependencies.

### 2. `backend/.env`
Added four environment variables:
```env
REDIS_HOST=redis-<project>.redis.cache.windows.net
REDIS_PORT=6380
REDIS_PASSWORD=<primary-access-key>
REDIS_SSL=true
```

### 3. `backend/server.py` — `SessionManager` class

**Before:** Four in-memory Python dicts (`_sessions`, `_session_states`, `_session_metadata`, `_message_counts`).

**After:** Only `_sessions` (hot cache) remains in memory.  Everything else uses Redis:

| Data | Before | After |
|---|---|---|
| Session state (AgentSession JSON) | `_session_states` dict | `session:{id}:state` (STRING) |
| Metadata (title, user, timestamps) | `_session_metadata` dict | `session:{id}:metadata` (HASH) |
| Message count | `_message_counts` dict | `session:{id}:message_count` (STRING/INCR) |

**Key implementation details:**
- `connect()` / `close()` — lifecycle methods using `redis.asyncio.Redis`
- All public methods are now `async` (were sync before)
- `get_session()` — checks in-memory cache first, falls back to Redis `GET` + `AgentSession.from_dict()`
- `create_session()` — uses a Redis pipeline for atomic writes
- `list_sessions()` — uses `SCAN` with pattern `session:*:metadata`
- `save_session_state()` — called after every agent turn, serialises to Redis

### 4. `backend/server.py` — Call site updates

All callers of `SessionManager` methods needed `await` added:
- `create_session()` in `POST /sessions` and `POST /chat`
- `get_session()` in `GET /sessions/{id}/history` and `POST /chat`
- `delete_session()` in `DELETE /sessions/{id}`
- `update_session()` in `PUT /sessions/{id}`
- `save_session_state()` and `increment_message_count()` in `stream_agent_response()`
- `_assert_session_owner()` was converted to async (queries Redis HASH instead of dict)

### 5. `backend/server.py` — Lifespan

Added `await session_manager.connect()` at startup and `await session_manager.close()` at shutdown.

### 6. Terraform (`infra/modules/user_seat/main.tf`)

Added `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` (as secret), and `REDIS_SSL` env vars to the backend Container App.

## Verification

After starting the backend, send a chat message and verify Redis keys:

```bash
redis-cli -h <host> -p 6380 --tls -a <key>
> KEYS session:*
# Should show session:*:state, session:*:metadata, session:*:message_count
> HGETALL session:<id>:metadata
# Should show title, created_at, last_activity, user_id
> GET session:<id>:message_count
# Should show "2" after one turn
```

Restart the backend and send another message to the same session — it should resume without losing history.
