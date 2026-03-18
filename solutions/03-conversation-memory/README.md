# Solution 03 — Conversation Memory

This solution implements conversation memory in three parts: the summarisation prompt, the store initialization, and the create endpoint.

## Part 1: Summarisation prompt

Replace the contents of `backend/prompts/conversation_memory.j2` with:

```
You are a conversation memory assistant. Your job is to create a concise,
meaningful summary of a customer support conversation.

Rules:
- Capture the main topic, customer intent, and resolution (if any).
- Include key entities: order IDs, product names, dates, names.
- Keep the summary to 2-4 sentences maximum.
- Write in third person, past tense.
- Do NOT include greetings, filler, or meta-commentary.
- Output ONLY the summary text, nothing else.

Example:
  "Customer inquired about order ORD-001 shipping status. The order was
   confirmed as shipped with tracking number 1Z999AA1, estimated delivery
   Jan 25, 2026."
```

### Why this prompt works

- **Third person, past tense** — produces consistent, professional summaries
- **2-4 sentences** — enough detail for semantic search without noise
- **Key entities** — order IDs, product names, dates improve search recall
- **No filler** — stripped greetings/meta means the embedding captures only meaningful content
- **Example** — gives the LLM a concrete target format

### Alternative approaches to try

**PII-stripping variant:**
```
...
- Replace all personal names with "[Customer]" and "[Agent]".
- Replace email addresses, phone numbers, and addresses with "[REDACTED]".
...
```

**Bullet-point variant:**
```
...
- Format the summary as 3-5 bullet points.
- First bullet: main topic/intent.
- Subsequent bullets: key details and resolution.
...
```

## Part 2: Store initialization in lifespan

In `backend/server.py`, in the `lifespan` function:

**Startup** — add after conversation history init:
```python
await memory_store.initialize()
logger.info("Conversation memory store initialized (PostgreSQL)")
```

**Shutdown** — add alongside other store closures:
```python
await memory_store.close()
logger.info("Conversation memory store closed")
```

## Part 3: `create_memory` endpoint

In `backend/server.py`, replace the `create_memory()` function body with:

```python
@app.post("/memories", response_model=MemorySummaryResponse, status_code=201)
async def create_memory(
    request: CreateMemoryRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Create a conversation memory (summary + embedding) for a conversation.

    Fetches the full conversation from Cosmos DB, runs the summarisation agent,
    generates an embedding, and stores the result in PostgreSQL.
    """
    # 1. Validate ownership and fetch the conversation
    conversation = await conversation_store.get_conversation(
        request.conversation_id, current_user.user_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = conversation.get("messages", [])
    if not messages:
        raise HTTPException(status_code=422, detail="Conversation has no messages to summarise")

    # 2. Run memory agent (summarise + embed)
    result = await memory_agent.create_memory(
        conversation_messages=messages,
        title=conversation.get("title"),
    )

    # 3. Persist to PostgreSQL
    row = await memory_store.create_memory(
        conversation_id=request.conversation_id,
        user_id=current_user.user_id,
        summary=result.summary,
        embedding=result.embedding,
        source_title=conversation.get("title"),
        message_count=conversation.get("message_count", len(messages)),
    )

    return _row_to_memory_response(row)
```

## Key Concepts

- **Summarise-then-embed:** The MemoryAgent first produces a natural-language summary via LLM, then generates a vector embedding of that summary. This means semantic search quality depends directly on your prompt.
- **Upsert pattern:** `memory_store.create_memory` uses `ON CONFLICT … DO UPDATE` — re-memorising a conversation replaces the old summary and embedding.
- **Prompt iteration:** The summarisation prompt is the most impactful lever. Small changes (e.g., adding PII stripping, changing length, switching to bullet points) significantly affect what gets stored and how well search works.
