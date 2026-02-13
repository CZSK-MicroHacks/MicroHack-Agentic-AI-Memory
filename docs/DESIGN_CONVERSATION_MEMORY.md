# Conversation Memory — Feature Design

## 1. Overview

Conversation Memory creates a **summary + vector embedding** for each Conversation History item (stored in Cosmos DB). This enables semantic search across past conversations without loading full message payloads.

**Relationship**: One Conversation History item → one Conversation Memory item.

```
┌─────────────────────────┐       1:1       ┌──────────────────────────┐
│  Conversation History   │ ──────────────► │   Conversation Memory    │
│  (Cosmos DB)            │                 │   (PostgreSQL + pgvector)│
│                         │                 │                          │
│  • id (session_id)      │                 │  • id (UUID)             │
│  • user_id              │                 │  • conversation_id (FK)  │
│  • title                │                 │  • user_id               │
│  • messages[]           │                 │  • summary (text)        │
│  • message_count        │                 │  • embedding (vector)    │
│  • created_at           │                 │  • created_at            │
│  • updated_at           │                 │  • updated_at            │
└─────────────────────────┘                 └──────────────────────────┘
```

---

## 2. PostgreSQL Schema

Uses the existing `pgvector/pgvector:pg16` container (`pgsql/docker-compose.yml`).  
Connection: `postgresql://app:app_pwd@localhost:5432/appdb`.

### 2.1 Migration SQL (`pgsql/init/001_conversation_memory.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE conversation_memory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT        NOT NULL,          -- matches Cosmos doc "id" (session_id)
    user_id         TEXT        NOT NULL,          -- partition key, same as Cosmos
    summary         TEXT        NOT NULL,          -- agent-generated summary
    embedding       vector(1536) NOT NULL,         -- text-embedding-3-small dimension
    source_title    TEXT,                          -- snapshot of conversation title at creation time
    message_count   INT         NOT NULL DEFAULT 0,-- snapshot of message count
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_conversation_memory UNIQUE (conversation_id, user_id)
);

-- Index for fast user-scoped listing
CREATE INDEX idx_memory_user ON conversation_memory (user_id, created_at DESC);

-- IVFFlat index for vector similarity search (cosine distance)
-- Rebuild after bulk inserts with: REINDEX INDEX idx_memory_embedding;
CREATE INDEX idx_memory_embedding ON conversation_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Key decisions:**
- `UNIQUE (conversation_id, user_id)` enforces the 1:1 relationship and lets us upsert.
- `vector(1536)` matches Azure OpenAI `text-embedding-3-small`. If using `text-embedding-3-large` (3072 dims), adjust accordingly.
- IVFFlat chosen for the index because the dataset is small; can switch to HNSW if list size grows.

### 2.2 Docker Compose Update

Add an init script volume mount so the schema is created automatically on first `docker compose up`:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    container_name: pg-local
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app_pwd
      POSTGRES_DB: appdb
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init:/docker-entrypoint-initdb.d   # ← new line
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d appdb"]
      interval: 5s
      timeout: 3s
      retries: 10
```

---

## 3. Backend Architecture

### 3.1 New Module: `backend/conversation_memory.py`

Responsibilities:
- PostgreSQL connection pool management (asyncpg)
- CRUD operations on `conversation_memory` table
- Vector search query

```
class ConversationMemoryStore:
    """Async CRUD + vector search over PostgreSQL + pgvector."""

    async def initialize() -> None
        # Create asyncpg pool, ensure table exists

    async def close() -> None
        # Close pool

    async def create_memory(
        conversation_id: str,
        user_id: str,
        summary: str,
        embedding: list[float],
        source_title: str | None,
        message_count: int,
    ) -> dict
        # INSERT ... ON CONFLICT (conversation_id, user_id) DO UPDATE
        # Returns the created/updated row

    async def get_memory(conversation_id: str, user_id: str) -> dict | None
        # Point read by conversation_id + user_id

    async def list_memories(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]
        # List all memories for a user, newest first
        # Returns: id, conversation_id, user_id, summary, source_title,
        #          message_count, created_at, updated_at
        # (excludes embedding from list queries for payload size)

    async def delete_memory(conversation_id: str, user_id: str) -> bool
        # DELETE by conversation_id + user_id

    async def search(user_id: str, query_embedding: list[float], limit: int = 10) -> list[dict]
        # Vector similarity search scoped to user_id
        # SELECT *, 1 - (embedding <=> $1) AS similarity
        # FROM conversation_memory
        # WHERE user_id = $2
        # ORDER BY embedding <=> $1
        # LIMIT $3
        # Returns rows with similarity score
```

### 3.2 New Module: `backend/memory_agent.py`

A lightweight agent whose sole job is to summarize a conversation and produce an embedding. Uses Microsoft Agent Framework (`ChatAgent`) + Azure OpenAI.

```
class MemoryAgent:
    """Summarizes a conversation and generates its embedding."""

    def __init__(self, chat_client, embedding_client):
        self._summarizer = ChatAgent(
            name="MemorySummarizer",
            instructions=SUMMARIZATION_PROMPT,
            chat_client=chat_client,
        )
        self._embedding_client = embedding_client

    async def create_memory(
        self,
        conversation_messages: list[dict],
        title: str | None = None,
    ) -> MemoryResult:
        """
        1. Feed conversation messages to the summarizer agent
        2. Get a concise summary back
        3. Generate embedding from the summary text
        4. Return MemoryResult(summary, embedding)
        """
```

#### Summarization Prompt

```
You are a conversation memory assistant. Your job is to create a concise,
meaningful summary of a customer support conversation.

Rules:
- Capture the main topic, customer intent, and resolution (if any).
- Include key entities: order IDs, product names, dates, names.
- Keep the summary to 2-4 sentences maximum.
- Write in third person, past tense.
- Do NOT include greetings, filler, or meta-commentary.

Example:
  "Customer inquired about order ORD-001 shipping status. The order was
   confirmed as shipped with tracking number 1Z999AA1, estimated delivery
   Jan 25, 2026."
```

#### Embedding Generation

Uses Azure OpenAI Embeddings API directly (not via agent framework — the framework is for chat completion, embeddings are a separate API call):

```python
from openai import AsyncAzureOpenAI

embedding_client = AsyncAzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_ad_token_provider=token_provider,
    api_version="2024-06-01",
)

response = await embedding_client.embeddings.create(
    model=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
    input=summary_text,
)
embedding = response.data[0].embedding  # list[float], 1536 dims
```

### 3.3 New Environment Variables

```env
# PostgreSQL
PG_HOST=localhost
PG_PORT=5432
PG_USER=app
PG_PASSWORD=app_pwd
PG_DATABASE=appdb

# Azure OpenAI Embedding model
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

### 3.4 New Python Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "asyncpg>=0.30.0",          # async PostgreSQL driver
    "openai>=1.40.0",           # Azure OpenAI embeddings
]
```

---

## 4. API Design

All endpoints are scoped to the authenticated user (via `Authorization: Bearer ...` in cloud deployments; local mock mode uses explicit `X-Mock-User-ID`).

### 4.1 Create Memory

```
POST /memories
```

**Request Body:**
```json
{
  "conversation_id": "abc-123"
}
```

**Flow:**
1. Validate user owns the conversation (read from Cosmos DB)
2. Fetch full conversation messages from Cosmos DB
3. Run `MemoryAgent.create_memory(messages, title)` → summary + embedding
4. Upsert into `conversation_memory` table
5. Return created memory

**Response (201):**
```json
{
  "id": "uuid-...",
  "conversation_id": "abc-123",
  "user_id": "user-alice",
  "summary": "Customer inquired about order ORD-001...",
  "source_title": "Order Inquiry",
  "message_count": 6,
  "created_at": "2026-02-10T12:00:00Z",
  "updated_at": "2026-02-10T12:00:00Z"
}
```

**Error cases:**
- `404` — conversation not found or not owned by user
- `422` — conversation has no messages (nothing to summarize)

**Note:** This is an intentionally synchronous API for simplicity. The summarization + embedding step typically takes 2-4 seconds. The frontend should show a loading indicator during this time. A future optimization could use `BackgroundTasks` to make it fire-and-forget, but for the MVP, synchronous is simpler and gives immediate feedback.

### 4.2 List Memories

```
GET /memories?limit=50&offset=0
```

**Response (200):**
```json
[
  {
    "id": "uuid-...",
    "conversation_id": "abc-123",
    "user_id": "user-alice",
    "summary": "Customer inquired about order ORD-001...",
    "source_title": "Order Inquiry",
    "message_count": 6,
    "created_at": "2026-02-10T12:00:00Z",
    "updated_at": "2026-02-10T12:00:00Z"
  }
]
```

### 4.3 Get Single Memory

```
GET /memories/{conversation_id}
```

**Response (200):** Same shape as a single item from the list.  
**Error:** `404` if not found.

### 4.4 Delete Memory

```
DELETE /memories/{conversation_id}
```

**Response (200):**
```json
{ "message": "Memory deleted successfully" }
```

**Error:** `404` if not found.

### 4.5 Vector Search

```
POST /memories/search
```

**Request Body:**
```json
{
  "query": "order shipping status",
  "limit": 10
}
```

**Flow:**
1. Generate embedding for the query text using the same embedding model
2. Run cosine similarity search in `conversation_memory` scoped to `user_id`
3. Return top N results with similarity scores

**Response (200):**
```json
{
  "query": "order shipping status",
  "results": [
    {
      "id": "uuid-...",
      "conversation_id": "abc-123",
      "summary": "Customer inquired about order ORD-001 shipping status...",
      "source_title": "Order Inquiry",
      "similarity": 0.92,
      "created_at": "2026-02-10T12:00:00Z"
    }
  ]
}
```

---

## 5. Server Integration (`server.py`)

### 5.1 Initialization

```python
# In server.py — alongside existing stores
from conversation_memory import ConversationMemoryStore
from memory_agent import MemoryAgent

memory_store = ConversationMemoryStore()
memory_agent = MemoryAgent(chat_client=chat_client, embedding_client=embedding_client)

@app.on_event("startup")
async def startup_event():
    await conversation_store.initialize()
    await memory_store.initialize()       # ← new

@app.on_event("shutdown")
async def shutdown_event():
    await conversation_store.close()
    await memory_store.close()            # ← new
```

### 5.2 Endpoint Registration

Five new routes registered on the existing `app`:

```python
@app.post("/memories",             status_code=201)    # create
@app.get("/memories")                                   # list
@app.get("/memories/{conversation_id}")                  # get one
@app.delete("/memories/{conversation_id}")               # delete
@app.post("/memories/search")                            # vector search
```

All share the same `Depends(get_current_user)` auth pattern.

### 5.3 Cascade Delete

When a conversation is deleted via `DELETE /conversations/{id}`, also delete its memory:

```python
@app.delete("/conversations/{conversation_id}")
async def delete_conversation(...):
    # existing: delete from Cosmos DB
    deleted = await conversation_store.delete_conversation(...)
    # new: also remove memory from PostgreSQL
    await memory_store.delete_memory(conversation_id, current_user.user_id)
    ...
```

---

## 6. Frontend Changes

### 6.1 New Client Methods (`client.ts`)

```typescript
// Add to AGUIClient class:

async createMemory(conversationId: string): Promise<MemorySummary> { ... }
async listMemories(limit?: number, offset?: number): Promise<MemorySummary[]> { ... }
async deleteMemory(conversationId: string): Promise<void> { ... }
async searchMemories(query: string, limit?: number): Promise<MemorySearchResult> { ... }
```

New TypeScript interfaces:

```typescript
export interface MemorySummary {
  id: string;
  conversation_id: string;
  user_id: string;
  summary: string;
  source_title: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface MemorySearchResult {
  query: string;
  results: Array<MemorySummary & { similarity: number }>;
}
```

### 6.2 Conversation History Item — "Memorize" Button (`app.ts`)

Add a third action button to each conversation history item in the sidebar, alongside the existing "Rename" and "Delete" buttons:

```
┌──────────────────────────────────────────┐
│ 📝 Order Inquiry                         │
│ 6 msgs · 2h ago            ✏️  🧠  🗑️   │
└──────────────────────────────────────────┘
                                ↑
                          New "Memorize" button
                          (Material Symbol: "psychology")
```

**Behavior:**
- Click triggers `POST /memories` with the conversation ID
- Shows a small spinner on the button while the API call is in progress
- On success: icon changes to a checkmark (`check_circle`) briefly, then reverts; optionally show a toast/snackbar
- On error: show error tooltip
- If a memory already exists for this conversation, the button could show a filled icon (`psychology_alt`) to indicate it, and re-clicking re-generates the memory (upsert)

**State tracking:**
```typescript
@state() private memorizingConversationId: string | null = null;
@state() private memorizedConversationIds: Set<string> = new Set();
```

On component mount or after listing conversations, fetch `GET /memories` to populate `memorizedConversationIds` so the UI can show which conversations already have memories.

### 6.3 Memory Search UI (Optional / Phase 2)

A search input in the sidebar header or a dedicated "Memory" section:

```
┌─────────────────────────────────────┐
│  🔍 Search memories...              │
│                                     │
│  Results:                           │
│  ┌─────────────────────────────────┐│
│  │ Order ORD-001 inquiry (92%)     ││
│  │ Customer asked about...         ││
│  └─────────────────────────────────┘│
│  ┌─────────────────────────────────┐│
│  │ Return request (87%)            ││
│  │ Customer requested return...    ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
```

Clicking a search result navigates to the corresponding conversation.

---

## 7. Data Flow Diagrams

### 7.1 Memory Creation Flow

```
User clicks "Memorize" button on Conversation History item
    │
    ▼
Frontend: POST /memories { conversation_id }
    │
    ▼
Backend (server.py):
    ├─ 1. Validate user owns conversation (Cosmos DB read)
    ├─ 2. Fetch full messages from Cosmos DB
    ├─ 3. Call MemoryAgent.create_memory(messages, title)
    │       ├─ 3a. Summarizer agent (ChatAgent) → summary text
    │       └─ 3b. Embeddings API → vector(1536)
    ├─ 4. Upsert into conversation_memory (PostgreSQL)
    └─ 5. Return { id, summary, ... }
    │
    ▼
Frontend: Show success indicator, update memorizedConversationIds
```

### 7.2 Vector Search Flow

```
User types query into search input
    │
    ▼
Frontend: POST /memories/search { query, limit: 10 }
    │
    ▼
Backend (server.py):
    ├─ 1. Generate embedding for query text (Embeddings API)
    ├─ 2. Run cosine similarity search in PostgreSQL
    │       WHERE user_id = current_user
    │       ORDER BY embedding <=> query_embedding
    │       LIMIT 10
    └─ 3. Return ranked results with similarity scores
    │
    ▼
Frontend: Display ranked results, link to conversations
```

---

## 8. File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `pgsql/docker-compose.yml` | **Modify** | Add init script volume mount |
| `pgsql/init/001_conversation_memory.sql` | **New** | Schema migration with pgvector |
| `backend/conversation_memory.py` | **New** | `ConversationMemoryStore` — asyncpg CRUD + vector search |
| `backend/memory_agent.py` | **New** | `MemoryAgent` — summarization agent + embedding generation |
| `backend/server.py` | **Modify** | Add 5 memory endpoints, initialize stores, cascade delete |
| `backend/pyproject.toml` | **Modify** | Add `asyncpg`, `openai` dependencies |
| `frontend/src/client.ts` | **Modify** | Add memory API methods + types |
| `frontend/src/app.ts` | **Modify** | Add "Memorize" button, state tracking, search UI |

---

## 9. Open Questions / Future Considerations

1. **Embedding model choice**: Design assumes `text-embedding-3-small` (1536 dims). If using `text-embedding-3-large` (3072 dims), update the schema `vector(3072)` and index accordingly.

2. **Re-summarization**: Current design upserts (replaces) memory on re-click. Alternative: append versioned summaries. Upsert is simpler and recommended for MVP.

3. **Batch creation**: The prompt mentions "usually once a day as a background process." A future `POST /memories/batch` endpoint could iterate all conversations without memories and create them. Out of scope for this design.

4. **Memory-augmented chat**: A natural next step — when the user sends a message, search memories for relevant context and inject it into the agent's system prompt (RAG pattern). Out of scope for this design.

5. **Index tuning**: IVFFlat with `lists=100` is fine for <10K rows. For larger datasets, switch to HNSW or increase list count.

6. **Async processing**: For MVP, memory creation is synchronous (2-4s). If latency becomes an issue, use FastAPI's `BackgroundTasks` to return `202 Accepted` immediately and poll for completion.
