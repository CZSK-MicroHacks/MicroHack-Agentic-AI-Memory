# PRD: Create Memory Endpoint — `POST /memories`

## Purpose

The `POST /memories` endpoint takes a conversation (stored in Cosmos DB), runs it through a summarisation agent to produce a concise summary and vector embedding, and persists the result in PostgreSQL for semantic search.

This is the orchestration layer that ties together: Cosmos DB (source) → MemoryAgent (processing) → PostgreSQL (destination).

## Endpoint Specification

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **Path** | `/memories` |
| **Request body** | `CreateMemoryRequest` |
| **Response** | `MemorySummaryResponse` (HTTP 201) |
| **Auth** | Bearer token → `current_user: User` via `Depends(get_current_user)` |

## Request Model

Already defined in `server.py`:

```python
class CreateMemoryRequest(BaseModel):
    conversation_id: str  # ID of the conversation to memorise
```

## Response Model

Already defined in `server.py`:

```python
class MemorySummaryResponse(BaseModel):
    id: str
    conversation_id: str
    user_id: str
    summary: str
    source_title: str | None = None
    message_count: int = 0
    created_at: str
    updated_at: str
```

## Available Objects

These are already imported and instantiated at module level in `server.py`:

| Object | Type | Purpose |
|--------|------|---------|
| `conversation_store` | `ConversationHistoryStore` | Read conversations from Cosmos DB |
| `memory_agent` | `MemoryAgent` | Summarise a conversation + generate embedding |
| `memory_store` | `ConversationMemoryStore` | Persist summary + embedding to PostgreSQL |
| `_row_to_memory_response()` | `function` | Convert a DB row dict → `MemorySummaryResponse` |

## Implementation Steps

The function receives `request: CreateMemoryRequest` and `current_user: User`.

### Step 1: Fetch the conversation

Call `conversation_store.get_conversation(request.conversation_id, current_user.user_id)`.

- If it returns `None` → raise `HTTPException(status_code=404, detail="Conversation not found")`

### Step 2: Validate the conversation has messages

Read the `"messages"` field from the conversation document.

- If the messages list is empty → raise `HTTPException(status_code=422, detail="Conversation has no messages to summarise")`

### Step 3: Run the memory agent

Call `memory_agent.create_memory()` with:

- `conversation_messages` — the messages list from Step 2
- `title` — the conversation's `"title"` field (may be `None`)

This returns a `MemoryResult` with two fields:
- `result.summary` — the LLM-generated summary text
- `result.embedding` — the vector embedding (`list[float]`, 3072 dimensions)

### Step 4: Persist to PostgreSQL

Call `memory_store.create_memory()` with:

- `conversation_id` — from the request
- `user_id` — from `current_user.user_id`
- `summary` — from the memory agent result
- `embedding` — from the memory agent result
- `source_title` — the conversation's `"title"` field
- `message_count` — from the conversation's `"message_count"` field, falling back to `len(messages)`

This returns a dict representing the inserted/updated database row.

### Step 5: Return the response

Convert the row dict to the API response using `_row_to_memory_response(row)`.

## Error Handling

- **404** — conversation not found or not owned by user
- **422** — conversation has no messages
- **500** — unexpected failures (let FastAPI handle)

## Data Flow Diagram

```
POST /memories { conversation_id: "abc-123" }
  │
  ▼
┌─────────────────────────────────┐
│ 1. conversation_store           │  Cosmos DB
│    .get_conversation(id, user)  │──────────────▶ conversation document
└─────────────────────────────────┘                    │
                                                       ▼
                                        ┌──────────────────────────────┐
                                        │ 2. memory_agent              │
                                        │    .create_memory(messages)   │
                                        │    → LLM summarisation       │
                                        │    → embedding generation    │
                                        └──────────────────────────────┘
                                                       │
                                            MemoryResult(summary, embedding)
                                                       │
                                                       ▼
                                        ┌──────────────────────────────┐
                                        │ 3. memory_store              │  PostgreSQL
                                        │    .create_memory(...)       │──────────────▶ row
                                        └──────────────────────────────┘
                                                       │
                                                       ▼
                                        _row_to_memory_response(row) → HTTP 201
```
