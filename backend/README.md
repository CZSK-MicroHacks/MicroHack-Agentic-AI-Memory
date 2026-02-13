
# backend — AG-UI Customer Support Server

FastAPI backend that streams AG-UI events over SSE, keeps server-side session
history, and persists conversations, memories, and user profiles.

## Features

- AG-UI SSE streaming (`/chat`) with tool-call events
- Server-side sessions via `AgentThread` + `ChatMessageStore`
- Durable conversation history in Azure Cosmos DB
- Conversation memory summaries + vector search (PostgreSQL + pgvector)
- User profile memory extraction and CRUD (Cosmos DB)
- Azure Entra ID bearer token auth (production)
- Explicit mock auth via `X-Mock-User-ID` (local development)

## Architecture

```
┌──────────────────────────────────────────────┐
│  FastAPI (server.py)                         │
│  - /chat (SSE AG-UI events)                  │
│  - /sessions (in-memory SessionManager)      │
│  - /conversations (Cosmos DB history)        │
│  - /memories (Postgres + pgvector)           │
│  - /profile (Cosmos DB user profile)         │
└───────────────┬──────────────────────────────┘
				│
				▼
┌──────────────────────────────────────────────┐
│  Agents                                       │
│  - CustomerSupportAgent (tool: get_order_status)
│  - MemoryAgent (summary + embedding)          │
│  - ProfileAgent (profile extraction)          │
└──────────────────────────────────────────────┘
```

### Key files

| File | Purpose |
|---|---|
| `server.py` | FastAPI app, SSE chat, sessions, REST endpoints |
| `conversation_history.py` | Cosmos DB conversation history store |
| `conversation_memory.py` | Postgres + pgvector memory store |
| `user_profile_memory.py` | Cosmos DB user profile store |
| `memory_agent.py` | Conversation summarizer + embedding |
| `profile_agent.py` | User profile extraction agent |
| `auth.py` | Entra JWT auth + local mock auth |
| `client.py` | CLI test client for AG-UI streaming |

## Running

```bash
cd backend
uv run server.py
```

API docs: `http://localhost:8000/docs`

Optional CLI client:

```bash
cd backend
uv run client.py
```

## Configuration

Required:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_NAME`

Optional (memory + profile):

- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` (default: `text-embedding-3-large`)
- `COSMOS_ENDPOINT` (default: `http://localhost:8081/`)
- `COSMOS_KEY`
- `COSMOS_DATABASE_NAME` / `COSMOS_CONTAINER_NAME`
- `COSMOS_UPM_DATABASE_NAME` / `COSMOS_UPM_CONTAINER_NAME`
- `COSMOS_EMULATOR_DISABLE_SSL_VERIFY`
- `PG_HOST` / `PG_PORT` / `PG_DATABASE`
- `PG_AUTH_MODE` (`password` or `managed_identity`, default `password`)
- `PG_AAD_PRINCIPAL_NAME` (required when `PG_AUTH_MODE=managed_identity`, unless `PG_USER` is set)
- `PG_USER` / `PG_PASSWORD` (used in `password` mode)
- `PG_SSLMODE` (optional override; default is `require` for `managed_identity`, `prefer` for `password`)
- `AGUI_SERVER_URL` (for `client.py`)

Auth configuration:

- `AUTH_MODE` (`entra` or `mock`, default `entra`)
- `ENTRA_TENANT_ID` (required in `entra` mode)
- `ENTRA_AUDIENCE` (required in `entra` mode; backend API client ID)
- `ENTRA_ISSUER` (optional override)
- `ENTRA_REQUIRED_SCOPES` (optional comma-separated scopes)
- `ENTRA_REQUIRED_ROLES` (optional comma-separated app roles)

## Core endpoints

- `POST /chat` — SSE stream of AG-UI events
- `GET /me` — current authenticated user
- `POST /sessions` / `GET /sessions` / `DELETE /sessions/{id}`
- `GET /conversations` / `GET /conversations/{id}`
- `POST /memories` / `POST /memories/search`
- `GET /profile` / `POST /profile/generate` / `POST /profile/generate-all`

