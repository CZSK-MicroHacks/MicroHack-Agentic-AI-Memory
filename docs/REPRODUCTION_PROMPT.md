# AG-UI Customer Support Chat — Full Reproduction Prompt

Use this prompt with GitHub Copilot agent mode to reproduce the entire project from scratch.

---

## Prompt

Build a full-stack customer support chat application using the **AG-UI protocol** and **Microsoft Agent Framework** with durable conversation history in **Azure Cosmos DB**, conversation memory with vector search in **PostgreSQL + pgvector**, and user profile memory in **Cosmos DB**. The app has a Python/FastAPI backend and a TypeScript/Lit frontend, deployed to **Azure Container Apps** via Terraform.

### Prerequisites (already installed, do not install)

- Python 3.11+ with `uv` package manager
- Node.js 18+
- Azure CLI authenticated (`az login`)
- Azure OpenAI deployment available (with text-embedding-3-large for embeddings)
- Docker (for local Cosmos DB emulator and PostgreSQL)
- Terraform >= 1.5.0

### Project Structure

```
ag-ui-demo/
├── .gitignore
├── README.md
├── DESIGN_CONVERSATION_MEMORY.md
├── DESIGN_USER_PROFILE_MEMORY.md
├── backend/
│   ├── .dockerignore
│   ├── .env.example
│   ├── .env                  # (from .env.example, user fills in)
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── auth.py
│   ├── client.py
│   ├── conversation_history.py
│   ├── conversation_memory.py
│   ├── memory_agent.py
│   ├── profile_agent.py
│   ├── server.py
│   └── user_profile_memory.py
├── frontend/
│   ├── Dockerfile
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── main.ts
│       ├── app.ts
│       ├── auth.ts
│       ├── client.ts
│       ├── converters.ts
│       ├── a2ui/
│       │   ├── types.ts
│       │   ├── processor.ts
│       │   └── surface-renderer.ts
│       └── templates/
│           └── shipping-status.ts
├── pgsql/
│   ├── docker-compose.yml
│   └── init/
│       └── 001_conversation_memory.sql
└── infra/
    ├── main.tf
    ├── variables.tf
    ├── terraform.tfvars
    ├── identity.tf
    ├── monitoring.tf
    ├── aca.tf
    ├── postgres.tf
    ├── cosmosdb.tf
    ├── redis.tf
    ├── roles.tf
    └── outputs.tf
```

---

## Step 1: Backend — Project Configuration

Create `backend/pyproject.toml` with:

```toml
[project]
name = "ag-ui-demo"
version = "0.1.0"
description = "AG-UI Customer Support Demo"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "agent-framework-ag-ui>=1.0.0b260130",
    "aiohttp>=3.9.0",
    "asyncpg>=0.30.0",
    "azure-cosmos>=4.9.0",
    "azure-identity>=1.26.0b1",
    "openai>=1.40.0",
    "python-dotenv>=1.2.1",
]
```

Create `backend/.env.example` with Azure OpenAI vars plus Cosmos DB emulator vars:
- `AZURE_OPENAI_ENDPOINT` — user's Azure OpenAI endpoint
- `AZURE_OPENAI_DEPLOYMENT_NAME` — e.g. `gpt-4o`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` — e.g. `text-embedding-3-large`
- `COSMOS_ENDPOINT=http://localhost:8081/`
- `COSMOS_KEY=C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==` (Cosmos emulator well-known key)
- `COSMOS_DATABASE_NAME=conversationhistory`
- `COSMOS_CONTAINER_NAME=conversationhistory`
- `COSMOS_UPM_DATABASE_NAME=userprofiles`
- `COSMOS_UPM_CONTAINER_NAME=userprofiles`
- `COSMOS_EMULATOR_DISABLE_SSL_VERIFY=1`
- `PG_HOST=localhost`
- `PG_PORT=5432`
- `PG_USER=app`
- `PG_PASSWORD=app_pwd`
- `PG_DATABASE=appdb`

Run `cd backend && uv sync` to install dependencies.

---

## Step 2: Backend — Mock Authentication (`auth.py`)

Create a mock auth module with:
- A `User` Pydantic model with fields: `user_id`, `display_name`, `email`, `avatar_url` (optional), `initials`
- A `MOCK_USERS` dict containing 3 hardcoded users: `user-alice` (Alice Johnson, AJ), `user-bob` (Bob Smith, BS), `user-charlie` (Charlie Lee, CL)
- Default user: `user-alice`
- A FastAPI dependency `get_current_user()` that reads `X-User-ID` from request header; falls back to default user if missing; raises 401 for unknown users
- Add a docstring noting migration path: replace with Azure Entra ID JWT/Bearer token validation via `azure-identity`/MSAL middleware

---

## Step 3: Backend — Conversation History Store (`conversation_history.py`)

Create an async CRUD wrapper around Azure Cosmos DB for durable conversation history.

**Architecture distinction** (document in docstrings):
- **SessionManager** = live, ephemeral, in-memory `AgentThread` + `ChatMessageStore` for the current turn
- **ConversationHistoryStore** = durable JSON documents in Cosmos DB, full conversation records

**Class: `ConversationHistoryStore`**
- Constructor reads env vars (endpoint, key, database, container) with emulator defaults. SSL verification controlled by `COSMOS_EMULATOR_DISABLE_SSL_VERIFY` env var.
- Uses `azure.cosmos.aio.CosmosClient` (async client)
- Partition key: `/user_id`

**Methods:**
1. `async initialize()` — `create_database_if_not_exists` + `create_container_if_not_exists` (idempotent)
2. `async close()` — close the Cosmos client
3. `async save_conversation(session_id, user_id, messages, title, metadata)` — upsert a document. Preserves `created_at` from existing doc if it exists. Document shape: `{id, user_id, title, created_at, updated_at, message_count, messages, metadata}`
4. `async get_conversation(session_id, user_id)` — point-read by id + partition key, returns `None` on not found
5. `async list_conversations(user_id, limit=50, offset=0)` — SQL query returning lightweight summaries (no messages body), ordered by `updated_at DESC`
6. `async delete_conversation(session_id, user_id)` — hard delete with **emulator workaround**: the Cosmos DB vnext-preview emulator returns malformed HTTP response (`null` body) for DELETE operations. After catching the error, verify deletion via a point-read fallback — if the item is gone, treat it as success.
7. `async update_title(session_id, user_id, title)` — read-modify-upsert to patch title + updated_at

**CRITICAL — Azure Cosmos DB AAD auth for production:**
The constructor must support **both** key-based auth (local emulator) and AAD auth (Azure deployment). When `COSMOS_KEY` env var is empty/unset, use `DefaultAzureCredential()` from `azure.identity` as the credential. This is **mandatory** because Azure Cosmos DB accounts deployed with `local_authentication_disabled = true` reject key-based auth entirely. The managed identity must have the "Cosmos DB Built-in Data Contributor" role assigned (see Terraform `roles.tf`).

```python
from azure.identity import DefaultAzureCredential

# In constructor:
self._key = key or os.getenv("COSMOS_KEY", "")
credential: Any
if self._key:
    credential = self._key  # local emulator
else:
    credential = DefaultAzureCredential()  # Azure managed identity

self._client = CosmosClient(url=self._endpoint, credential=credential, ...)
```

---

## Step 3b: PostgreSQL + pgvector Setup

### Local Docker Setup (`pgsql/docker-compose.yml`)

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
      - ./init:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d appdb"]
      interval: 5s
      timeout: 3s
      retries: 10

  pgadmin:
    image: dpage/pgadmin4:8
    container_name: pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@example.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - db

volumes:
  pgdata:
```

### Schema (`pgsql/init/001_conversation_memory.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS conversation_memory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT         NOT NULL,
    user_id         TEXT         NOT NULL,
    summary         TEXT         NOT NULL,
    embedding       vector(3072) NOT NULL,   -- text-embedding-3-large
    source_title    TEXT,
    message_count   INT          NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_conversation_memory UNIQUE (conversation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_user ON conversation_memory (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_embedding ON conversation_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

## Step 3c: Conversation Memory Store (`conversation_memory.py`)

Async CRUD + vector-similarity search over PostgreSQL + pgvector.

**Class: `ConversationMemoryStore`**
- Constructor reads env vars: `PG_HOST` (default `localhost`), `PG_PORT` (default `5432`), `PG_USER` (default `app`), `PG_PASSWORD` (default `app_pwd`), `PG_DATABASE` (default `appdb`)
- Uses `asyncpg` connection pool (min 2, max 10)

**Methods:**
1. `async initialize()` — create pool, ensure `vector` extension + `conversation_memory` table exist
2. `async close()` — close pool
3. `async create_memory(conversation_id, user_id, summary, embedding, source_title, message_count)` — `INSERT ... ON CONFLICT DO UPDATE`. Format embedding as pgvector literal: `"[" + ",".join(str(v) for v in embedding) + "]"`, cast as `$4::vector`
4. `async get_memory(conversation_id, user_id)` — point read
5. `async list_memories(user_id, limit, offset)` — newest first, excludes embedding column
6. `async delete_memory(conversation_id, user_id)` — returns bool
7. `async search(user_id, query_embedding, limit)` — cosine similarity: `1 - (embedding <=> $1::vector) AS similarity`, ordered by `embedding <=> $1::vector`, scoped to user

---

## Step 3d: Memory Agent (`memory_agent.py`)

Summarises a conversation and generates its vector embedding.

**Uses:**
- `ChatAgent` from Agent Framework for summarisation (same Azure OpenAI deployment)
- `AsyncAzureOpenAI` from `openai` SDK for embeddings (deployment: `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`, default `text-embedding-3-large`)

**Summarisation prompt:** Concise 2-4 sentence summary, third person past tense, captures main topic, customer intent, resolution, key entities (order IDs, dates, names). No greetings or filler.

**Class: `MemoryAgent`**
- Constructor takes `chat_client` (AzureOpenAIChatClient), creates internal `ChatAgent` for summarisation and `AsyncAzureOpenAI` for embeddings using `DefaultAzureCredential` + `get_bearer_token_provider`
- `async create_memory(conversation_messages, title)` → `MemoryResult(summary, embedding)`
  1. `_format_conversation()` — builds readable transcript from messages
  2. `_summarize()` — runs ChatAgent with summarisation prompt
  3. `_embed(text)` — generates embedding vector via Azure OpenAI

---

## Step 3e: User Profile Memory Store (`user_profile_memory.py`)

Persists a single evolving profile document per user in Cosmos DB.

**Storage:** Cosmos DB database `userprofiles`, container `userprofiles`, partition key `/user_id`.

**CRITICAL — Same AAD auth pattern as conversation_history.py:** When `COSMOS_KEY` is empty, use `DefaultAzureCredential()`.

**Class: `UserProfileMemoryStore`**
- Constructor reads `COSMOS_ENDPOINT`, `COSMOS_KEY`, `COSMOS_UPM_DATABASE_NAME`, `COSMOS_UPM_CONTAINER_NAME`
- Profile skeleton sections: `basic_info` {}, `interests` [], `habits` [], `preferences` {}, `status` {}, `facts` []

**Methods:**
1. `async initialize()` — create database + container if not exist
2. `async close()` — close client
3. `async get_profile(user_id)` — point read, returns None if not found
4. `async upsert_profile(user_id, profile_sections, source_conversation?)` — create or replace with version increment, append source_conversation to audit trail
5. `async patch_profile(user_id, updates)` — partial update, merge provided fields
6. `async delete_profile(user_id)` — hard delete with same emulator workaround as conversation_history

---

## Step 3f: Profile Agent (`profile_agent.py`)

Extracts personal facts from conversations and merges into user profile.

**Prompt:** Analyses conversation transcript against existing profile. Outputs structured JSON with `profile_changed`, `change_summary`, `facts_added/updated/removed`, and the full `profile` object. Rules: conservative extraction, only facts about the user, no inference, deduplicate.

**Class: `ProfileAgent`**
- Constructor takes `chat_client`, creates internal `ChatAgent` with extraction prompt
- `async extract_profile(existing_profile, conversation_messages, conversation_id)` → `ProfileExtractionResult`
  1. `_build_prompt()` — existing profile JSON + conversation transcript
  2. `_run_agent()` — ChatAgent stream, collect full text
  3. `_parse_response()` — strip markdown fences, parse JSON, ensure all sections exist

---

## Step 4: Backend — Main Server (`server.py`)

Create a FastAPI application with AG-UI protocol support, server-side session management, Cosmos DB persistence, conversation memory (PostgreSQL), and user profile memory (Cosmos DB).

**Module-level initialisation:**
```python
from conversation_history import ConversationHistoryStore
from conversation_memory import ConversationMemoryStore
from memory_agent import MemoryAgent
from user_profile_memory import UserProfileMemoryStore
from profile_agent import ProfileAgent

conversation_store = ConversationHistoryStore()
memory_store = ConversationMemoryStore()
profile_store = UserProfileMemoryStore()
# memory_agent and profile_agent initialised after chat_client is created
```

### 4a. SessionManager class

Manages live in-memory sessions with `AgentThread` + `ChatMessageStore`.

**Fields:**
- `_sessions: dict[str, AgentThread]`
- `_session_metadata: dict[str, dict]` — title, created_at, last_activity, user_id
- `_max_sessions` (default 1000), `_max_messages` (default 100)

**Methods:**
- `create_session(session_id, title, user_id)` — creates empty `ChatMessageStore(messages=[])` + `AgentThread(message_store=...)`. LRU eviction when at capacity.
- `create_session_from_history(session_id, history_messages, title, user_id)` — **critical for conversation resume**. Converts stored message dicts `{role, content}` back to `ChatMessage` objects (import from `agent_framework._threads`), creates pre-populated `ChatMessageStore(messages=chat_messages)` + `AgentThread`. Only hydrates `user`, `assistant`, `system` roles (skip `tool` role).
- `get_session(session_id, auto_create)` — lookup + update last_activity
- `delete_session(session_id)` — remove from both dicts
- `update_session(session_id, title)` — update metadata
- `get_session_info(session_id)` → `SessionInfo` pydantic model
- `list_sessions(user_id)` — filter by user
- `get_session_history(session_id)` — reads `message_store.list_messages()`, converts each `ChatMessage` to dict with `role`, `content`, plus extracted `tool_calls` and `tool_results` from `msg.contents` (checking `content.type == 'function_call'` and `'function_result'`)

### 4b. Tools

One tool: `get_order_status(order_id: str) -> dict`
- Hardcoded orders: ORD-001 (shipped, tracking 1Z999AA1, ETA Jan 25 2026), ORD-002 (processing, no tracking, ETA Jan 23 2026), ORD-003 (delivered, tracking 1Z999AA3, delivered Jan 20)
- Returns `{trackingNumber, currentStepIcon, eta}` — matches the A2UI shipping status template data model
- Status icon mapping: shipped→`local_shipping`, processing→`pending`, delivered→`check_circle`, not_found→`error`

### 4c. Agent Configuration

- Use `AzureOpenAIChatClient` with `DefaultAzureCredential()`, reading endpoint + deployment from env
- Create `ChatAgent` named `"CustomerSupportAgent"` with instructions telling it to always call `get_order_status` when order IDs are mentioned, never guess, and remember conversation context
- Register `tools=[get_order_status]`

### 4d. FastAPI App & Endpoints

**Lifecycle:**
- `startup_event` → `await conversation_store.initialize()`, `await memory_store.initialize()`, `await profile_store.initialize()`
- `shutdown_event` → close all three stores

**Auth helper:** `_assert_session_owner(session_id, user_id)` — raises 403 if session's user_id doesn't match

**Endpoints:**
- `GET /me` — return current user profile
- `POST /sessions` — create session
- `GET /sessions` — list sessions for current user
- `GET /sessions/{id}` — get session info
- `GET /sessions/{id}/history` — get message history
- `PUT /sessions/{id}` — update title
- `DELETE /sessions/{id}` — delete session **and** cascade delete from Cosmos DB via `conversation_store.delete_conversation()`
- `GET /conversations` — list conversations from Cosmos DB (summaries)
- `GET /conversations/{id}` — get full conversation with messages
- `PUT /conversations/{id}` — update conversation title
- `DELETE /conversations/{id}` — hard delete from Cosmos DB, **cascade delete associated memory** via `memory_store.delete_memory()`

### 4d2. Conversation Memory Endpoints (PostgreSQL + pgvector)

- `POST /memories` — create summary + embedding for a conversation. Fetches conversation from Cosmos DB, runs `memory_agent.create_memory()`, persists to PostgreSQL via `memory_store.create_memory()`
- `GET /memories` — list memories for current user
- `GET /memories/{conversation_id}` — get single memory
- `DELETE /memories/{conversation_id}` — delete memory
- `POST /memories/search` — semantic search: generates embedding for query text via `memory_agent._embed()`, then `memory_store.search()`. Returns results with similarity scores.

### 4d3. User Profile Memory Endpoints (Cosmos DB)

- `GET /profile` — get current user's profile (404 if none)
- `POST /profile/generate` — extract profile from one conversation: reads conversation, runs `profile_agent.extract_profile()`, upserts if changed
- `POST /profile/generate-all` — extract profile from all conversations: lists conversations, skips already-processed (tracked via `source_conversations[]`), processes new ones sequentially
- `PUT /profile` — manual edit (partial update)
- `DELETE /profile` — delete profile

### 4e. Chat Endpoint (`POST /chat`)

This is the core AG-UI streaming endpoint. Request body: `{messages: [{role, content}], thread_id?: string}`.

**Session resolution logic (critical for conversation resume):**
1. `session_id = request.thread_id or uuid4()`
2. If session exists in `session_manager._sessions` → verify ownership
3. If session NOT in memory → **check Cosmos DB**: `await conversation_store.get_conversation(session_id, user_id)`
   - If conversation found with messages → `session_manager.create_session_from_history(...)` to hydrate thread with full prior context
   - If no conversation found → `session_manager.create_session(...)` (empty, brand new)
4. Extract last user message from request
5. Stream response via `stream_agent_response()`

**`stream_agent_response()` function:**
- Generates AG-UI SSE events: `RunStartedEvent` → `TextMessageContentEvent` (deltas) + `ToolCallStartEvent`/`ToolCallResultEvent`/`ToolCallEndEvent` → `RunFinishedEvent`
- Uses `agent.run_stream(user_message, thread=thread)` — framework handles history automatically
- **After `RunFinishedEvent`**: call `_persist_conversation(session_id, user_id, title)` which reads session history via `session_manager.get_session_history()` and upserts to Cosmos DB via `conversation_store.save_conversation()`
- Tool call deduplication via `seen_tools` set
- Error handling → `RunErrorEvent`

**Response:** `StreamingResponse` with `media_type="text/event-stream"`, headers include `X-Session-ID`

### 4f. CORS

Allow all origins, credentials, methods, headers (development config).

---

## Step 5: Backend — CLI Client (`client.py`)

Create a simple interactive CLI chat client using `AGUIChatClient` from `agent_framework_ag_ui`:
- Connects to `AGUI_SERVER_URL` env var (default `http://localhost:8000/chat`)
- Creates `ChatAgent(chat_client=AGUIChatClient(endpoint=...))` + `agent.get_new_thread()`
- REPL loop: read input, stream response via `agent.run_stream()`, print text + tool calls/results
- Exit on "exit"/"quit"/"bye"

---

## Step 6: Frontend — Project Configuration

Create `frontend/package.json`:
```json
{
  "name": "frontenda2uinative",
  "private": true,
  "version": "0.1.0",
  "description": "A2UI Native Rendering frontend",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "lit": "^3.2.1",
    "marked": "^17.0.1"
  },
  "devDependencies": {
    "typescript": "^5.7.2",
    "vite": "^6.0.7"
  }
}
```

Create `frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "lib": ["ESNext", "DOM", "DOM.Iterable"],
    "moduleResolution": "bundler",
    "strict": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "useDefineForClassFields": false,
    "experimentalDecorators": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src"]
}
```

Create `frontend/vite.config.ts` with:
- Dev server on port 5175
- Proxy `/api` → `http://localhost:8000` (strip `/api` prefix via rewrite)
- Build target: `esnext`

Run `cd frontend && npm install`.

---

## Step 7: Frontend — HTML Shell (`index.html`)

Create `frontend/index.html` with:
- Google Fonts Material Symbols Outlined (variable font) with **explicit `icon_names` parameter** containing all used icons: `account_circle,add,arrow_forward,auto_awesome,chat_bubble,check,check_circle,circle,close,dark_mode,delete,edit,error,help,history,info,inventory_2,light_mode,local_shipping,menu,more_vert,open_in_new,package_2,pending,schedule,send,support_agent`
- Google Fonts Inter (weights 300-700)
- CSS custom properties for a full neutral palette (--n-0 through --n-100), primary palette (--p-10 through --p-100), error palette, status colors (shipped/processing/delivered/not_found)
- Uses CSS `light-dark()` function for theme support
- `color-scheme` toggle via body class (`light`/`dark`), with `prefers-color-scheme: dark` media query default
- Entry point: `<a2ui-native-app>` custom element + `<script type="module" src="./src/main.ts">`

---

## Step 8: Frontend — Auth Module (`src/auth.ts`)

Create a mock auth module:
- `User` interface: `user_id, display_name, email, avatar_url, initials`
- `CURRENT_USER_ID = 'user-alice'`
- `getAuthHeaders()` returns `{ 'X-User-ID': CURRENT_USER_ID }`
- Docstring noting migration: replace with MSAL.js `acquireTokenSilent()` + Bearer token

---

## Step 9: Frontend — AG-UI SSE Client (`src/client.ts`)

Create the API client class `AGUIClient`:

**Types:**
- `AGUIEvent` — `{type: string, [key]: unknown}`
- `StreamCallbacks` — `onTextContent, onToolCallStart, onToolCallResult, onToolCallEnd, onError, onFinished`
- `SessionInfo` — `session_id, title, created_at, message_count, last_activity`
- `ToolCallRecord` — `call_id, name, arguments?`
- `ToolResultRecord` — `call_id, result`
- `SessionHistoryMessage` — `role, content, tool_calls?, tool_results?`
- `ConversationSummary` — `id, user_id, title, created_at, updated_at, message_count`
- `ConversationDetail` extends `ConversationSummary` — adds `messages: SessionHistoryMessage[], metadata`

**Methods:**
- `getMe()` — `GET /me`
- Session CRUD: `listSessions()`, `createSession(title?)`, `getSession(id)`, `updateSession(id, title)`, `deleteSession(id)`, `getSessionHistory(id)`
- Conversation CRUD: `listConversations(limit?, offset?)`, `getConversation(id)`, `updateConversation(id, title)`, `deleteConversation(id)`
- `sendMessage(message, threadId, callbacks)` — `POST /chat` with SSE streaming. Reads `X-Session-ID` from response header. Parses SSE lines (`data: {...}`), dispatches to callbacks based on event type. Returns `{sessionId}`.

All requests include `...getAuthHeaders()`.

---

## Step 10: Frontend — A2UI Type System (`src/a2ui/types.ts`)

Define TypeScript types for the A2UI v0.8 protocol:

- `BoundValue` — `{literalString?, literalNumber?, literalBoolean?, path?}`
- `ComponentAction` — `{name, context?: ActionContextItem[]}`
- `ChildrenDef` — `{explicitList?: string[], template?: {dataBinding, componentId}}`
- Component types: `TextComponent`, `IconComponent`, `ImageComponent`, `ButtonComponent`, `CardComponent`, `ColumnComponent`, `RowComponent`, `ListComponent`, `DividerComponent`
- `ComponentDef` — `{id, weight?, component: {Text?, Icon?, Image?, Button?, Card?, Column?, Row?, List?, Divider?}}`
- `DataEntry` — `{key, valueString?, valueNumber?, valueBoolean?, valueMap?: DataEntry[]}`
- Message types: `SurfaceUpdateMessage`, `DataModelUpdateMessage`, `BeginRenderingMessage`, `DeleteSurfaceMessage`
- Union type: `A2UIMessage`

---

## Step 11: Frontend — A2UI Processor (`src/a2ui/processor.ts`)

Create a pure-data processor implementing the client-side A2UI pipeline:

**`SurfaceState` interface:** `components: Map<string, ComponentDef>`, `dataModel: Record<string, unknown>`, `rootId: string | null`, `ready: boolean`

**`A2UIProcessor` class:**
- `processMessages(messages)` / `processMessage(msg)` — handles `surfaceUpdate` (populate component map), `dataModelUpdate` (populate data model), `beginRendering` (mark ready), `deleteSurface`
- `getReadySurfaces()` — returns Map of ready surfaces
- `resolveDataPath(surfaceId, path)` — traverses data model by `/`-separated path
- Private helpers: `ensurePath()`, `applyContents()` (converts `DataEntry[]` into nested object)

---

## Step 12: Frontend — A2UI Surface Renderer (`src/a2ui/surface-renderer.ts`)

Create a Lit web component `<a2ui-surface>` that recursively renders an A2UI `SurfaceState`:

**Properties:** `surface: SurfaceState | null`, `surfaceId: string`

**Recursive rendering:** `renderComponent(id, dataContextPath?)` dispatches to component-specific methods based on which key is present in `component`:
- `Card` → bordered card with `a2ui-card-body` padding wrapper
- `Column` → flex column with gap classes (small/medium/large)
- `Row` → flex row with alignment (start/center/end/stretch) + distribution (spaceBetween/center/end) classes
- `Text` → `<p>` with usage hint CSS class (h1-h5, body, caption)
- `Icon` → Material Symbols Outlined span
- `Image` → `<img>`
- `Button` → primary/secondary styled button, dispatches `a2ui-action` CustomEvent
- `List` → flex container, vertical/horizontal
- `Divider` → `<hr>` horizontal or vertical

**BoundValue resolution:** literal values returned directly; `path` values resolved against surface data model. Supports data context path for template-based list rendering.

**Styles:** All styles in Shadow DOM CSS, using `light-dark()` with the same CSS custom property palette as the main app. Must redeclare `.material-symbols-outlined` font-face rules inside Shadow DOM.

---

## Step 13: Frontend — Shipping Status Template (`src/templates/shipping-status.ts`)

Create a declarative A2UI surface template for order shipping status visualization:

**Export:** `SHIPPING_STATUS_TEMPLATE: ComponentDef[]`

**Component tree:**
```
Card(root)
└── Column(main-column, gap=medium)
    ├── Row(header) → Icon(package_2) + Text("Package Status", h3)
    ├── Text(tracking-number, path=/trackingNumber, caption)
    ├── Divider
    ├── Column(steps, gap=small)
    │   ├── Row(step1) → Icon(check_circle) + Text("Order Placed", body)
    │   ├── Row(step2) → Icon(check_circle) + Text("Shipped", body)
    │   ├── Row(step3) → Icon(path=/currentStepIcon) + Text("Out for Delivery", h4)
    │   └── Row(step4) → Icon(circle) + Text("Delivered", caption)
    └── Row(eta) → Icon(schedule) + Text(path=/eta, body)
```

Data bindings: `/trackingNumber`, `/currentStepIcon`, `/eta` — these are filled from the `get_order_status` tool result.

---

## Step 14: Frontend — Tool Result Converters (`src/converters.ts`)

Create a converter system that transforms tool results into A2UI messages:

**`inflateSurfaceTemplate(template, dataModel, surfaceId)`** — takes a reusable A2UI template + flat data model object, produces 3 A2UI messages: `surfaceUpdate → dataModelUpdate → beginRendering`

**Converter registry** (`Map<string, converter>`):
- `get_order_status` → uses `SHIPPING_STATUS_TEMPLATE`, pass-through data model (backend already returns matching shape)

**`convertToolResult(toolName, resultJson, surfaceId)`** — looks up converter, returns A2UI messages or null

**`convertGenericResult(toolName, resultJson, surfaceId)`** — fallback renderer that shows tool name + raw JSON in a Card with Text component

---

## Step 15: Frontend — Main App Component (`src/app.ts`)

Create the main Lit web component `<a2ui-native-app>` — this is the largest file.

### 15a. Data Types

- `ToolCallInfo` — `{id, name, result?, status: 'running'|'completed', surface?: SurfaceState, surfaceId?}`
- `ChatMessage` — `{id, role: 'user'|'assistant', content, toolCalls: ToolCallInfo[], isStreaming?}`

### 15b. State Properties

- `messages: ChatMessage[]`
- `isLoading: boolean`
- `sessionId: string | null`
- `sidebarOpen: boolean` (default true)
- `sessions: SessionInfo[]`
- `editingSessionId / editingTitle` — for inline rename
- `currentUser: User | null`
- `conversations: ConversationSummary[]` — from Cosmos DB
- `editingConversationId / editingConversationTitle` — for inline rename
- `activeConversationId: string | null` — currently viewed conversation from history

### 15c. Lifecycle

`connectedCallback()` → focus input, `fetchCurrentUser()`, `refreshSessions()`, `refreshConversations()`

### 15d. Layout

Three-column layout: sidebar (260px) | main (flex). Main has header (52px) | messages area (scrollable) | input area.

**Sidebar sections:**
1. Header with "Chat" title, + (new session) button, close button
2. **Sessions** section header + session list
3. **History** section header + conversation list
4. User profile card at bottom (avatar initials + display name)

### 15e. Session Management

- `refreshSessions()` — `client.listSessions()`
- `handleCreateSession()` — create + select
- `handleSelectSession(id)` — load session history, deselect conversation, rebuild messages
- `startRenameSession()` / `commitRename()` / `handleRenameKeydown()` — inline rename with Enter/Escape
- `handleDeleteSession()` — delete + cleanup
- `newChat()` — clear sessionId + activeConversationId + messages

### 15f. Conversation History Management

- `refreshConversations()` — `client.listConversations()`
- `handleSelectConversation(id)` — load full conversation from Cosmos DB, deselect session, rebuild messages using `buildChatMessagesFromHistory()`
- `resumeConversation(conversationId)` — sets `sessionId = conversationId` AND `activeConversationId = conversationId` so follow-up messages go to the same thread
- `startRenameConversation()` / `commitConversationRename()` / `handleConversationRenameKeydown()` — inline rename
- `handleDeleteConversation()` — delete + cleanup

### 15g. buildChatMessagesFromHistory (shared helper)

Converts `SessionHistoryMessage[]` (from either session or conversation history) into `ChatMessage[]` with reconstructed A2UI surfaces:

1. **First pass:** collect tool results keyed by `call_id` from all messages
2. **Second pass:** build `ChatMessage` array:
   - Messages with `tool_calls` → create `ToolCallInfo` objects, reconstruct A2UI surfaces using `convertToolResult()` → `A2UIProcessor`, push to `pendingToolCalls`
   - Skip messages that only contain `tool_results` (non user/assistant)
   - For `user`/`assistant` messages → create `ChatMessage`, attach any pending tool calls to assistant messages

### 15h. Chat Flow (`send()`)

1. If `activeConversationId` set and no `sessionId` → call `resumeConversation()` first
2. Create user + assistant placeholder messages
3. Stream via `client.sendMessage(text, sessionId, callbacks)`
4. Callbacks:
   - `onTextContent` → append delta to assistant content
   - `onToolCallStart` → add running tool call indicator
   - `onToolCallResult` → convert to A2UI surface via `convertToolResult()` or `convertGenericResult()`, process through `A2UIProcessor`
   - `onToolCallEnd` → mark completed
   - `onFinished` → clear streaming state
5. After completion: if no sessionId, capture from response. Refresh sessions + conversations lists.

### 15i. Rendering

- **Session items:** `chat_bubble` icon, title (or `Chat {id.slice(0,8)}`), meta line (msg count + relative time), hover actions (edit/delete)
- **Conversation items:** `history` icon, same layout as sessions, hover actions (edit/delete)
- **Messages:** ChatGPT-style full-width rows with avatar (user=primary color / assistant=neutral), role label, tool call indicators (spinner while running, A2UI surface when completed), markdown-rendered text content (using `marked`), streaming cursor animation
- **Welcome screen:** centered logo + "How can I help you today?" + 3 suggestion buttons (ORD-001, ORD-002, ORD-003)
- **Input:** rounded input row with send button, disabled while loading

### 15j. Styling

ChatGPT-inspired design using `light-dark()` CSS function throughout:
- Sidebar: 260px, collapsible with slide animation
- Messages: max-width 768px, centered
- Theme toggle (dark_mode icon) in header
- Inline rename inputs with focus border
- Tool call indicators with spinner animation
- Streaming cursor blink animation
- Loading dots bounce animation
- Responsive: sidebar shrinks to 240px on mobile

---

## Step 16: Frontend — Entry Point (`src/main.ts`)

```typescript
import './app.js';
```

---

## Step 17: Start Local Services for Development

### Cosmos DB Emulator
```bash
docker run \
  --name cosmos-emulator \
  --detach \
  --publish 8081:8081 \
  --publish 1234:1234 \
  mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-preview
```

### PostgreSQL + pgvector
```bash
cd pgsql && docker compose up -d
```

---

## Step 18: Root Files

Create `.gitignore` ignoring: `__pycache__/`, `*.py[oc]`, `build/`, `dist/`, `wheels/`, `*.egg-info`, `.venv`, `.env`, `nohup.out`, `.vite/`, `node_modules/`

Create a `README.md` documenting the tech stack, prerequisites, setup steps (`uv sync`, `npm install`, `.env` config), and run commands (backend on port 8000, frontend on port 5175).

---

## Step 19: Test & Verify (Local Development)

1. Start PostgreSQL: `cd pgsql && docker compose up -d`
2. Start Cosmos DB emulator: (see Step 17)
3. Start backend: `cd backend && uv run python server.py` → http://localhost:8000
4. Start frontend: `cd frontend && npm run dev` → http://localhost:5175
5. Verify API docs at http://localhost:8000/docs
6. Test the following flows in the browser:
   - Send a message asking about ORD-001 → should see A2UI shipping status card
   - Check sidebar shows session in "Sessions" section
   - Wait for response to complete → should appear in "History" section (persisted to Cosmos DB)
   - Click a conversation in History → messages load with reconstructed A2UI surfaces
   - Send a follow-up message from loaded history → agent should have full prior context (not start fresh)
   - Rename/delete conversations via hover action buttons
   - Toggle dark/light theme
   - Create new chat, switch between sessions
   - Test memory endpoints: `POST /memories` with a conversation_id, then `POST /memories/search` with a query
   - Test profile endpoints: `POST /profile/generate` with a conversation_id, then `GET /profile`

---

## Key Architecture Decisions

1. **Session vs Conversation History:** Sessions are ephemeral in-memory `AgentThread` objects. Conversations are durable JSON documents in Cosmos DB. After every completed agent run, the session history is persisted to Cosmos via upsert.

2. **Conversation Resume (critical):** When a user sends a follow-up to a conversation loaded from history, the backend checks Cosmos DB if the session isn't in memory, hydrates an `AgentThread` with `ChatMessage` objects from stored history, then runs the agent with full prior context. This uses `ChatMessage` imported from `agent_framework._threads`.

3. **A2UI Native Rendering:** Tool results are not displayed as raw JSON. They are converted to A2UI component trees via declarative templates and rendered natively using a `<a2ui-surface>` web component. Adding new visualizations requires only a new template + data mapper — zero custom rendering code.

4. **Cosmos DB Emulator Workaround:** The vnext-preview emulator returns malformed HTTP for DELETE operations. The `delete_conversation` method works around this by verifying deletion via a point-read fallback.

5. **Auth:** Mock header-based auth (`X-User-ID`) with documented migration path to Azure Entra ID.

6. **Conversation Memory (pgvector):** Each conversation can be summarised into a 2-4 sentence summary + 3072-dim embedding (text-embedding-3-large). Stored in PostgreSQL with pgvector for cosine similarity search. One memory per conversation, scoped per user.

7. **User Profile Memory:** A single evolving Cosmos DB document per user. Facts extracted from conversations by a ProfileAgent (LLM-based), merged additively. Tracks source conversations for audit trail.

8. **Dual Cosmos DB Auth:** The code supports key-based auth (local emulator development) and AAD/managed identity auth (Azure deployment) via a single conditional in the constructor. When deployed to Azure with `local_authentication_disabled = true`, the `COSMOS_KEY` env var is intentionally omitted, triggering `DefaultAzureCredential`.

9. **Infrastructure as Code:** All Azure resources managed via Terraform in `infra/`. Container Apps start with hello-world images, then actual apps are deployed via `az containerapp up --source .` or `az acr build` + YAML update.

---

## Step 20: Azure Infrastructure (Terraform)

All Terraform files go in the `infra/` folder.

### Architecture

- **Resource Group:** `rg-mh-ai-memory` (or user-defined)
- **User-Assigned Managed Identity:** `id-{project}` — used by Container Apps for AAD auth to Cosmos DB and PostgreSQL
- **Log Analytics + Application Insights:** monitoring
- **Container Apps Environment + 2 Container Apps:** backend (port 8000) + frontend (port 80), hello-world placeholders
- **Azure Cosmos DB (NoSQL):** database `ag-ui-db`, containers `conversations` + `user_profiles`, **local auth disabled** (AAD-only)
- **PostgreSQL Flexible Server:** with pgvector extension, AAD admin = managed identity
- **Azure Cache for Redis:** Basic/C0, TLS 1.2 only
- **Cosmos DB Role Assignment:** "Built-in Data Contributor" for the managed identity

### Terraform Files

**main.tf** — providers (azurerm ~4.0, azuread ~3.0), data sources (`azurerm_client_config`, `azuread_client_config`), resource group

**variables.tf** — `subscription_id`, `resource_group_name`, `location`, `project_name`, `postgres_location` (separate variable — see deployment notes), `postgres_admin_login/password`, `postgres_sku`, `cosmosdb_throughput`, `redis_sku/family/capacity`, `tags`

**terraform.tfvars** — user fills in subscription_id, passwords, regions

**identity.tf** — `azurerm_user_assigned_identity`

**monitoring.tf** — `azurerm_log_analytics_workspace` + `azurerm_application_insights`

**aca.tf** — `azurerm_container_app_environment` + 2 × `azurerm_container_app` (hello-world, UserAssigned identity, external ingress)

**cosmosdb.tf** — `azurerm_cosmosdb_account` with `local_authentication_disabled = true`, database, 2 containers with `/user_id` partition key

**postgres.tf** — `azurerm_postgresql_flexible_server` in `var.postgres_location`, AAD + password auth, pgvector extension config, firewall for Azure services, database, AAD admin for managed identity

**redis.tf** — `azurerm_redis_cache`

**roles.tf** — `azurerm_cosmosdb_sql_role_assignment` with built-in "Cosmos DB Built-in Data Contributor" role (ID `00000000-0000-0000-0000-000000000002`)

**outputs.tf** — FQDNs, connection strings, managed identity IDs

### Deploy Infrastructure

```bash
cd infra
terraform init
terraform validate
terraform apply
```

---

## Step 21: Dockerfiles

### Backend Dockerfile (`backend/Dockerfile`)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-editable --no-hashes -o requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend Dockerfile (`frontend/Dockerfile`)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npx vite build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
RUN echo 'server { listen 80; root /usr/share/nginx/html; index index.html; location / { try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Backend `.dockerignore`

```
__pycache__
*.pyc
.env
.venv
.git
```

---

## Step 22: Deploy Applications to Azure Container Apps

### Build and Push Images

Use `az containerapp up --source .` to build images in ACR and deploy, or `az acr build` for manual builds:

```bash
# Frontend
cd frontend
az containerapp up --name ca-frontend-{project} --resource-group {rg} --source .

# Backend
cd backend
az acr build --registry {acr-name} --resource-group {rg} --image ca-backend-{project}:v1 --file Dockerfile .
```

### Configure Backend Container App

After deploying, update the backend container app with proper env vars via YAML:

```yaml
properties:
  template:
    containers:
      - name: backend
        image: {acr}.azurecr.io/ca-backend-{project}:{tag}
        resources:
          cpu: 0.5
          memory: 1Gi
        env:
          - name: AZURE_OPENAI_ENDPOINT
            value: "https://{your-openai}.openai.azure.com"
          - name: AZURE_OPENAI_DEPLOYMENT_NAME
            value: "gpt-4o"
          - name: AZURE_CLIENT_ID
            value: "{managed-identity-client-id}"
          - name: COSMOS_ENDPOINT
            value: "https://{cosmos-account}.documents.azure.com:443/"
          # NO COSMOS_KEY — AAD auth via managed identity
          - name: COSMOS_DATABASE_NAME
            value: "ag-ui-db"
          - name: COSMOS_CONTAINER_NAME
            value: "conversations"
          - name: COSMOS_UPM_DATABASE_NAME
            value: "ag-ui-db"
          - name: COSMOS_UPM_CONTAINER_NAME
            value: "user_profiles"
          - name: PG_HOST
            value: "{postgres}.postgres.database.azure.com"
          - name: PG_PORT
            value: "5432"
          - name: PG_USER
            value: "{postgres_admin_login}"
          - name: PG_PASSWORD
            value: "{postgres_admin_password}"
          - name: PG_DATABASE
            value: "appdb"
    scale:
      minReplicas: 1
      maxReplicas: 1
```

Apply with: `az containerapp update --name {app} --resource-group {rg} --yaml {file}`

---

## Deployment Findings & Troubleshooting Guide

These are critical issues discovered during deployment that will save significant debugging time.

### 1. PostgreSQL Region Restrictions (`LocationIsOfferRestricted`)

**Problem:** Azure PostgreSQL Flexible Server creation fails in many regions with error `LocationIsOfferRestricted`. Regions `eastus2` and `westus2` were both restricted.

**Solution:** Use a separate `postgres_location` variable. `northcentralus` worked. Also remove any `zone` constraint — Availability Zone 1 was unavailable in northcentralus.

**Important:** If a PostgreSQL server creation fails partway through, the resource name may become a "ghost" — Azure reserves the name but shows no resource. You must pick a new name (e.g., `pgflex-{project}` instead of `psql-{project}`).

### 2. Cosmos DB AAD-Only Auth (`Local Authorization is disabled`)

**Problem:** When Cosmos DB is deployed with `local_authentication_disabled = true` (the Terraform default for security), key-based auth is rejected. The app crashes at startup with `(Unauthorized) Local Authorization is disabled. Use an AAD token to authorize all requests.`

**Solution:** Both `conversation_history.py` and `user_profile_memory.py` must use `DefaultAzureCredential()` when `COSMOS_KEY` env var is empty. Set `AZURE_CLIENT_ID` env var on the Container App to the managed identity's client ID so `DefaultAzureCredential` picks the correct user-assigned identity.

**Do NOT set `COSMOS_KEY` in the container env vars.** The backend code detects empty key → uses AAD auth.

### 3. Cosmos DB Role Assignment Required

The managed identity needs the **"Cosmos DB Built-in Data Contributor"** data-plane role (not a regular Azure RBAC role). This is the built-in role with ID `00000000-0000-0000-0000-000000000002`. Assigned via `azurerm_cosmosdb_sql_role_assignment` in Terraform.

### 4. Frontend TypeScript Build Errors

**Problem:** Running `tsc` in Docker fails with `Module '"lit"' has no exported member 'css'` and similar errors due to TypeScript resolution differences.

**Solution:** Skip `tsc` in the Dockerfile. Use `npx vite build` directly — Vite handles TypeScript transpilation fine without strict type checking.

### 5. Backend Dependency Resolution (`agent-framework`)

**Problem:** Using `uv pip install --system -r pyproject.toml` in Docker resolves a dummy `agent-framework==0.0.0` package from PyPI instead of `agent-framework-core` from the private index.

**Solution:** Use `uv export --frozen --no-dev --no-editable --no-hashes -o requirements.txt` from `uv.lock` to get exact pinned dependencies, then `uv pip install --system --no-cache -r requirements.txt`. This ensures Docker gets the same packages as local development. **Requires** `uv.lock` to be committed and `COPY pyproject.toml uv.lock ./` in Dockerfile.

### 6. Container App Duplicate Containers

**Problem:** Running `az containerapp up` multiple times can add duplicate containers to the same Container App revision instead of replacing.

**Solution:** Use YAML-based updates with `az containerapp update --yaml` to define the exact single-container configuration.

### 7. Redis Import Case Sensitivity

**Problem:** When Terraform loses track of a partially-created Redis resource, `terraform import` fails with case sensitivity on the provider name: `Microsoft.Cache/Redis` (Azure default) vs `Microsoft.Cache/redis` (Terraform expectation).

**Solution:** Use lowercase `redis` in the import ID: `.../Microsoft.Cache/redis/{name}`

### 8. `AZURE_CLIENT_ID` Environment Variable

**Critically important:** When a Container App has both system-assigned and user-assigned managed identities, `DefaultAzureCredential` may pick the wrong one. Set `AZURE_CLIENT_ID={user-assigned-client-id}` to ensure the correct identity is used for Cosmos DB, PostgreSQL AAD, and Azure OpenAI auth.
