# Challenge 03 — Conversation Memory

## Overview

Your chat application now persists conversation history to Cosmos DB (Challenge 02). But raw conversation logs are not very useful for long-term recall — they're verbose, may contain sensitive data, and aren't searchable by meaning.

In this challenge, you will implement **conversation memory** — a pipeline that takes a conversation, summarises it using an LLM, generates a vector embedding, and stores the result in **PostgreSQL with pgvector**. This enables semantic search over past conversations.

The key creative element: **you design the summarisation prompt** that controls what gets remembered and how.

## What's Already in Place

- ✅ The `ConversationMemoryStore` class in `conversation_memory.py` — fully implemented CRUD + vector search over PostgreSQL
- ✅ The `MemoryAgent` class in `memory_agent.py` — reads your prompt, runs summarisation, generates embeddings
- ✅ The REST API endpoints for memories exist in `server.py` (`/memories/*`)
- ✅ PostgreSQL with pgvector is provisioned and configured (connection settings in `.env`)
- ✅ The `check_memory` agent tool works — it searches memories when users reference past conversations
- ❌ The summarisation prompt is empty (`backend/prompts/conversation_memory.j2`)
- ❌ The `POST /memories` endpoint is stubbed — returns 501
- ❌ The conversation memory store is not initialized at startup

## Your Task

You need to implement three things:

### Part 1: Write the summarisation prompt

Open `backend/prompts/conversation_memory.j2`. This is a Jinja2 template that serves as the **system prompt** for the summarisation LLM. It's currently empty.

Design a prompt that instructs the LLM to produce a concise, useful summary of a customer support conversation. Consider:

- **What to capture:** Main topic, customer intent, resolution, key entities (order IDs, product names, dates)
- **Summary length:** 2-4 sentences? A single paragraph? Bullet points?
- **PII handling:** Should personal names, emails, phone numbers be stripped or retained?
- **Tone/style:** Third person? Past tense? Neutral?
- **Search optimisation:** The summary will be embedded for semantic search — what phrasing makes it most findable?

> **💡 Tip:** Ask GitHub Copilot: *"Write a system prompt for summarising customer support conversations. The summary should be 2-4 sentences, capture the main topic and resolution, and exclude PII."*

> **🔬 Experiment:** After completing all parts, try creating memories for the same conversation with different prompts and compare the results in the UI. What style produces the best search results?

### Part 2: Initialize the memory store at startup

Open `backend/server.py` and find the `lifespan` function. The conversation memory store (`memory_store`) needs to be initialized at startup and closed at shutdown.

Add these lines in the appropriate places:

**Startup** (after the conversation history store init):
```python
await memory_store.initialize()
logger.info("Conversation memory store initialized (PostgreSQL)")
```

**Shutdown** (before or after other store closures):
```python
await memory_store.close()
logger.info("Conversation memory store closed")
```

### Part 3: Implement the `POST /memories` endpoint

Open `backend/server.py` and find the `create_memory()` function. This endpoint is called when a user clicks "Memorise" on a conversation in the UI. It orchestrates the full memory creation pipeline: fetch → summarise → embed → persist.

**Use the PRD document as your specification:**

👉 **[PRD.md](./PRD.md)** — Contains the full endpoint contract, available objects, step-by-step implementation guide, and data flow diagram.

> **💡 Tip:** Open the PRD in your editor and use GitHub Copilot to generate the implementation. You can reference the PRD directly in your Copilot prompt or use it as context.

> **💡 Tip:** Ask GitHub Copilot: *"Implement the create_memory endpoint based on the PRD specification. Use conversation_store, memory_agent, and memory_store."*

## Environment Variables

These are already configured in `backend/.env`:

| Variable | Description |
|----------|-------------|
| `PG_HOST` | PostgreSQL host |
| `PG_PORT` | PostgreSQL port (default: 5432) |
| `PG_USER` | PostgreSQL user |
| `PG_PASSWORD` | PostgreSQL password |
| `PG_DATABASE` | Database name (default: `appdb`) |
| `PG_AUTH_MODE` | `password` or `managed_identity` |

## Validation

After implementing all three parts:

1. **Restart the backend** (`uv run uvicorn server:app --reload`)
2. **Send a few messages** in the chat UI to create a conversation
3. **Click "Memorise"** on a conversation in the sidebar
4. **Check the Memories tab** in the UI — you should see a summary
5. **Try semantic search** — search for a topic you discussed and verify the memory is found
6. **Experiment with the prompt** — change the summarisation style and re-memorise to see how it affects results

## Success Criteria

- [ ] The summarisation prompt produces meaningful, concise summaries
- [ ] The memory store is initialised at application startup
- [ ] The `POST /memories` endpoint creates memories (summary + embedding) from conversations
- [ ] Memories appear in the UI Memories tab
- [ ] Semantic search (`POST /memories/search`) finds relevant memories
- [ ] The `check_memory` agent tool works — ask the agent about a previous conversation
