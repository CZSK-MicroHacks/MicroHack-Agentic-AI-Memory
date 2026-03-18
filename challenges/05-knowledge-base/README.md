# Challenge 05 — Knowledge Base (RAG via Azure AI Search)

## What You'll Build

Your agent can chat, check order statuses, recall past conversations, and manage user profiles — but it has **no access to the company knowledge base**. When a user asks *"What products were in my order?"* or *"What is your return policy?"*, the agent can only guess.

In this challenge you will connect the agent to **Azure AI Search** using the **RAG (Retrieval-Augmented Generation)** pattern. By the end, the agent will search indexed company documents (orders, products, policies) and respond with **cited, grounded answers**.

## Background: RAG and Its Flavors

**RAG** augments an LLM's generation with real-time retrieval from an external knowledge store. Instead of relying solely on training data, the agent first *retrieves* relevant documents and then *generates* a grounded answer.

This project supports two RAG approaches — you will implement the **agentic** path:

| | Classic RAG | Agentic RAG (MCP) |
|---|---|---|
| **How it works** | App code runs a hybrid search (keyword + vector + semantic ranking) against a single index and injects results into context | The agent itself decides *when* and *what* to search by calling an MCP tool; Azure AI Search's knowledge base retrieve API uses AI-driven reasoning across multiple indexes |
| **Scope** | Single pre-configured index (e.g. *orders*) | Multiple knowledge sources (e.g. *orders* **and** *policies*) |
| **Who controls retrieval** | Application logic | The LLM (via tool calling) |
| **Implementation** | REST call → parse response → inject into prompt | `MCPStreamableHTTPTool` exposed as an agent tool |

> The classic RAG client (`classic_rag_client.py`) is already fully implemented and can serve as a reference for how search results are structured.

## What's Already in Place

- ✅ Azure AI Search is provisioned with indexed data (orders + policies)
- ✅ `rag_client.py` contains helper utilities (`_AzureSearchAuth`, `_parse_mcp_rag_result`, `_derive_source_name`) — but the main factory function `create_rag_mcp_tool()` is **stubbed** (returns `None`)
- ✅ `agent_tools.py` has the `AgentTools` class with a `do_classic_rag` tool implemented — but RAG tools are **not registered** in the tool lists returned to the agent
- ✅ `server.py` has full `rag_mode` plumbing and lifecycle guards — MCP connection is safely skipped when the tool is `None`
- ✅ `prompts/customer_support.j2` instructs the agent about order status and memory tools — but has **no knowledge base instructions**
- ✅ Environment variables (`AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KNOWLEDGE_BASE_NAME`) are configured in `.env`

## Prerequisites: Load the Knowledge Base

Before you start coding, you need to populate Azure AI Search with the sample documents (orders and return policies). A setup script is provided:

```bash
cd setup/knowledgebase
pip install -r requirements.txt
python setup_search.py
```

This script creates two search indexes (`orders` and `return-policy`), uploads documents with vector embeddings, sets up knowledge sources, and creates a knowledge base that aggregates both sources.

**Required environment variables** (should already be in your `.env` or exported):

| Variable | Description |
|----------|-------------|
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint URL |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint (for generating embeddings) |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` | Embedding model deployment (default: `text-embedding-3-large`) |

> The script uses `DefaultAzureCredential` — make sure you're logged in via `az login`.

Once the script completes successfully you should see confirmation that both indexes are populated and the knowledge base is created. You can also verify in the Azure Portal under your AI Search resource → **Indexes** and **Knowledge bases**.

---

## Your Task

There are four parts. The **PRD document** describes the full specification:

👉 **[PRD.md](./PRD.md)** — Open it alongside your code and use it as context for GitHub Copilot.

> **💡 Approach:** You can feed the PRD to GitHub Copilot and implement all parts in a single pass. The PRD covers the function signature, MCP URL format, constructor parameters, tool registration, and prompt structure.

---

### Part 1: Implement `create_rag_mcp_tool()` in `rag_client.py`

The function is stubbed with `return None` and TODO comments. You need to make it create and return an `MCPStreamableHTTPTool` that connects to Azure AI Search's knowledge base MCP endpoint.

**Starting point:** Look at the existing helpers in the same file — `_AzureSearchAuth` handles authentication, `_parse_mcp_rag_result` handles result parsing, and `API_VERSION` is already defined. Your job is to wire them together into an `MCPStreamableHTTPTool`.

**Key decisions:**
- Read endpoint and knowledge base name from parameters or env vars
- Construct the MCP URL: `{endpoint}/knowledgebases/{kb_name}/mcp?api-version={API_VERSION}`
- Create an authenticated `httpx.AsyncClient` using `_AzureSearchAuth`
- Return a configured `MCPStreamableHTTPTool`

---

### Part 2: Register RAG tools in `agent_tools.py`

Two methods in the `AgentTools` class need updating — both have TODO comments:

1. **`all` property** — Add the MCP RAG tool (`self._rag_mcp_tool`) to the returned tool list so the default agent has access to it.

2. **`for_rag_mode()` method** — Implement mode switching so the correct RAG tool is included based on the `rag_mode` parameter (`"agentic"`, `"classic"`, or `"none"`).

**Starting point:** The `do_classic_rag` tool method is already implemented in the class. The `_rag_mcp_tool` is already stored as `self._rag_mcp_tool` in the constructor.

---

### Part 3: Add RAG instructions to the prompt template

Open `backend/prompts/customer_support.j2`. The agent currently doesn't know knowledge base tools exist. You need to tell it:

1. **What the RAG tools do** — Use Jinja2 conditional blocks (`{%- if rag_mode ... %}`) to describe the tools differently for agentic vs. classic mode
2. **When to use them** — Extend the TOOL SELECTION GUIDE with entries for product details and policy questions
3. **How to cite sources** — Add citation/annotation rules so the agent formats inline references using the `【search_idx:ref_id†source_name】` format

**Starting point:** Look at the Jinja2 TODO comment in the template. The `rag_mode` variable is passed to the template at render time. The `classic_rag_client.py` result structure shows what citation fields are available (`search_idx`, `ref_id`, `source_name`).

---

### Part 4: Verify server lifecycle

Open `backend/server.py` and check the `lifespan()` function. It already has guards (`if rag_mcp_tool is not None`) that skip MCP connection when the tool isn't configured.

**Once Part 1 returns a real tool instead of `None`, the connection is established automatically.** No code changes should be needed here — just verify the guards look correct.

## Environment Variables

Already configured in `backend/.env`:

| Variable | Description |
|----------|-------------|
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint URL |
| `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` | Knowledge base name (default: `customer-support-kb`) |
| `AZURE_SEARCH_ORDERS_INDEX` | Orders index name for classic search (default: `orders`) |

Authentication uses `DefaultAzureCredential` (Azure AD) — no API keys needed.

## Validation

1. **Restart the backend** — `uv run uvicorn server:app --reload`
2. **Check startup logs** — Look for: `RAG MCP tool connected (Azure AI Search knowledge base)`
3. **Ask about products:** *"What products were in order ORD-001?"* → detailed info with citations
4. **Ask about policies:** *"What is your return policy?"* → policy details with citations (agentic mode)
5. **Ask about order status:** *"What's the status of ORD-001?"* → still works (uses `get_order_status`, not RAG)

## Success Criteria

- [ ] `create_rag_mcp_tool()` returns a configured `MCPStreamableHTTPTool` (not `None`)
- [ ] RAG MCP tool connects successfully on server startup
- [ ] Agent uses knowledge base tools to answer product/shipping questions with citations
- [ ] Agent uses knowledge base tools to answer policy questions (agentic mode)
- [ ] Responses include inline citation annotations 【idx:ref†source】
- [ ] Existing tools (order status, memory, profile) continue to work
