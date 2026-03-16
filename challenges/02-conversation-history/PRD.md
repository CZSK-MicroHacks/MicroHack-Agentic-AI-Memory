# PRD: ConversationHistoryStore — Cosmos DB Conversation Persistence

## Purpose

The `ConversationHistoryStore` class provides an async CRUD interface for persisting full conversation history in Azure Cosmos DB. Each conversation is stored as a single JSON document, enabling the UI to display past conversations and allowing other features (memory, profile extraction) to read conversation data.

## Cosmos DB Structure

- **Database name:** Read from `COSMOS_DATABASE_NAME` env var (default: `conversationhistory`)
- **Container name:** Read from `COSMOS_CONTAINER_NAME` env var (default: `conversationhistory`)
- **Partition key:** `/user_id` — each user's conversations are co-located for efficient queries
- **Document ID:** `session_id` (== thread_id) — unique per conversation

## Document Schema

Each conversation document has this structure:

```json
{
  "id": "<session_id>",
  "user_id": "<user_id>",
  "title": "<optional conversation title>",
  "created_at": "<ISO 8601 UTC timestamp>",
  "updated_at": "<ISO 8601 UTC timestamp>",
  "message_count": 4,
  "messages": [
    { "role": "user", "content": "Hello" },
    { "role": "assistant", "content": "Hi! How can I help?" },
    { "role": "user", "content": "Tell me about returns" },
    { "role": "assistant", "content": "Our return policy..." }
  ],
  "metadata": {
    "agent_name": "CustomerSupportAgent",
    "model_deployment": "gpt-4o-mini",
    "api": "responses",
    "store": false
  }
}
```

## Configuration

The constructor should read these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `COSMOS_ENDPOINT` | `http://localhost:8081/` | Cosmos DB endpoint URL |
| `COSMOS_KEY` | `""` (empty) | Access key. If empty, use `DefaultAzureCredential` (AAD auth) |
| `COSMOS_DATABASE_NAME` | `conversationhistory` | Database name |
| `COSMOS_CONTAINER_NAME` | `conversationhistory` | Container name |
| `COSMOS_EMULATOR_DISABLE_SSL_VERIFY` | `0` | Set to `1` to disable SSL verification (for local emulator) |

### Authentication Logic

- If `COSMOS_KEY` is provided → use key-based auth (pass the key as credential)
- If `COSMOS_KEY` is empty → use `DefaultAzureCredential` from `azure.identity`

## Required Python Packages

These are already installed in the project:

- `azure-cosmos` — Cosmos DB async client (`azure.cosmos.aio.CosmosClient`, `azure.cosmos.aio.ContainerProxy`)
- `azure-identity` — `DefaultAzureCredential` for AAD authentication

## API Contract

### Constructor

```python
def __init__(
    self,
    endpoint: str | None = None,
    key: str | None = None,
    database_name: str | None = None,
    container_name: str | None = None,
)
```

- Parameters override environment variables when provided
- Creates a `CosmosClient` instance
- Sets `connection_verify` based on `COSMOS_EMULATOR_DISABLE_SSL_VERIFY`
- Stores a `_container: ContainerProxy | None` attribute (set during `initialize()`)

### `initialize() -> None`

Connect to the **existing** database and container (they are pre-provisioned by Terraform — do NOT create them).

- Use `client.get_database_client(name)` and `database.get_container_client(name)`
- Store the container reference for use by CRUD methods

### `close() -> None`

Close the underlying `CosmosClient` to release connections.

### `save_conversation(...) -> dict`

```python
async def save_conversation(
    self,
    session_id: str,
    user_id: str,
    messages: list[dict[str, Any]],
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]
```

**Behavior:**
1. Get current UTC timestamp in ISO 8601 format
2. Try to read the existing document (by `session_id` + `user_id` partition key) to preserve the original `created_at` timestamp. If not found, use the current timestamp.
3. Build a document with all fields from the schema above
4. **Upsert** the document (insert if new, replace if exists)
5. Return the upserted document

### `get_conversation(...) -> dict | None`

```python
async def get_conversation(self, session_id: str, user_id: str) -> dict[str, Any] | None
```

Point-read a single document by `session_id` (item ID) with `user_id` as the partition key. Return `None` if not found.

### `list_conversations(...) -> list[dict]`

```python
async def list_conversations(
    self,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]
```

**Behavior:**
- Query documents for a specific `user_id` using parameterized SQL
- Return lightweight summaries: `id`, `user_id`, `title`, `created_at`, `updated_at`, `message_count` (do NOT include `messages` body)
- Order by `updated_at` descending (newest first)
- Support pagination via `OFFSET` and `LIMIT`

### `delete_conversation(...) -> bool`

```python
async def delete_conversation(self, session_id: str, user_id: str) -> bool
```

Delete a document. Return `True` if deleted, `False` if not found.

### `update_title(...) -> dict | None`

```python
async def update_title(self, session_id: str, user_id: str, title: str) -> dict[str, Any] | None
```

Read the document, update its `title` and `updated_at` fields, upsert it back. Return the updated document, or `None` if not found.

## Integration Point: `_persist_turn()`

After implementing the class, you need to wire it into the chat flow. The `_persist_turn()` function in `server.py` is called after every agent turn. It should:

1. Construct message dicts: `{"role": "user", "content": user_message}` and `{"role": "assistant", "content": assistant_message}`
2. Build a metadata dict with `agent_name`, `model_deployment`, `api`, and `store` fields; include `rag_mode` if provided
3. Fetch the existing conversation via `conversation_store.get_conversation()` — if it exists, append new messages to old ones and merge metadata
4. Call `conversation_store.save_conversation()` with the accumulated data
5. Wrap everything in try/except to avoid crashing the chat stream on persistence failures
