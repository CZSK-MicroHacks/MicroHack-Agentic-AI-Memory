# Challenge 02 — Conversation History

## Overview

Your chat application works — users can talk to the AI agent and get responses. But when you refresh the page, all conversations disappear! That's because conversation history is not being persisted anywhere.

In this challenge, you will implement **durable conversation history** using **Azure Cosmos DB**. After completing this challenge, every conversation turn will be saved to Cosmos DB and the UI will display past conversations.

## What's Already in Place

- ✅ The backend is fully functional — chat works, sessions are managed in memory
- ✅ Cosmos DB is provisioned and configured (connection settings are in `.env`)
- ✅ The REST API endpoints for conversations exist in `server.py` (`/conversations/*`)
- ✅ The `_persist_turn()` function in `server.py` is called after every agent turn — but it's empty
- ✅ The `ConversationHistoryStore` class exists in `conversation_history.py` — but all methods are stubs

## Your Task

You need to implement two things:

### Part 1: Implement `ConversationHistoryStore` class

Open `backend/conversation_history.py`. This class is the data access layer for Cosmos DB. All methods are stubbed out with TODO comments.

**Use the PRD document as your specification:**

👉 **[PRD.md](./PRD.md)** — Contains the full API contract, document schema, and implementation requirements.

> **💡 Tip:** Open the PRD in your editor and use GitHub Copilot to generate the implementation. You can reference the PRD directly in your Copilot prompt or use it as context.

### Part 2: Implement `_persist_turn()` function

Open `backend/server.py` and find the `_persist_turn()` function. This function is called after every completed agent turn and should save the conversation to Cosmos DB using the store you just implemented.

It receives:
- `session_id` — the conversation/session identifier
- `user_id` — the user who owns the conversation
- `user_message` — what the user said
- `assistant_message` — what the agent replied
- `title` — optional conversation title
- `rag_mode` — optional RAG mode used

> **💡 Tip:** Ask GitHub Copilot: *"Implement _persist_turn to save conversation turns to Cosmos DB using conversation_store. It should append new messages to existing conversations and include metadata."*

## Environment Variables

These are already configured in `backend/.env`:

| Variable | Description |
|----------|-------------|
| `COSMOS_ENDPOINT` | Cosmos DB endpoint URL |
| `COSMOS_KEY` | Cosmos DB access key (empty = use AAD auth) |
| `COSMOS_DATABASE_NAME` | Database name (default: `conversationhistory`) |
| `COSMOS_CONTAINER_NAME` | Container name (default: `conversationhistory`) |

## Validation

After implementing both parts:

1. **Restart the backend** (`uv run uvicorn server:app --reload`)
2. **Send a few messages** in the chat UI
3. **Check the conversation list** appears in the UI sidebar
4. **Verify in Azure Portal:**
   - Navigate to your Cosmos DB account
   - Open **Data Explorer**
   - Select the `conversationhistory` database → `conversationhistory` container
   - You should see conversation documents with `id`, `user_id`, `messages`, `title`, etc.

## Success Criteria

- [ ] Chat conversations are persisted to Cosmos DB after each turn
- [ ] Conversation list endpoint (`GET /conversations`) returns saved conversations
- [ ] Individual conversations can be retrieved (`GET /conversations/{id}`)
- [ ] Documents are visible in Azure Portal Data Explorer
