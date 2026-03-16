# PRD: Knowledge Base RAG — Azure AI Search MCP Integration

## Purpose

The `create_rag_mcp_tool()` function creates an MCP (Model Context Protocol) tool that connects the agent to Azure AI Search's knowledge base retrieve API. This enables **agentic retrieval** — AI-driven reasoning across multiple knowledge sources (orders and policies) — as opposed to the classic single-index search.

The MCP tool is passed to the agent as one of its available tools. When the LLM decides it needs knowledge base information, it calls the MCP tool which communicates with Azure AI Search's MCP endpoint.

## Architecture

```
User Question → Agent (LLM) → MCP Tool → Azure AI Search KB → Results → Agent → Response with Citations
```

The key components:
- **`MCPStreamableHTTPTool`** — Framework class that wraps an MCP server as an agent tool
- **Azure AI Search MCP endpoint** — `{endpoint}/knowledgebases/{kb_name}/mcp?api-version={version}`
- **`_AzureSearchAuth`** — httpx auth class that injects Azure AD Bearer tokens
- **`_parse_mcp_rag_result()`** — Converts MCP output to `{content, citations}` format for the frontend

## Configuration

The function should read these environment variables (with parameter overrides):

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_SEARCH_ENDPOINT` | `""` | Azure AI Search endpoint URL (e.g., `https://my-search.search.windows.net`) |
| `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` | `customer-support-kb` | Name of the knowledge base in Azure AI Search |

### Authentication

Use `DefaultAzureCredential` from `azure.identity` for token acquisition. The `_AzureSearchAuth` class (already implemented in the file) wraps this into httpx auth that injects Bearer tokens for the scope `https://search.azure.com/.default`.

## API Version

Use the constant `API_VERSION` already defined at the top of `rag_client.py`:

```python
API_VERSION = "2025-11-01-Preview"
```

## MCP Endpoint URL

Construct the URL as:

```
{endpoint}/knowledgebases/{kb_name}/mcp?api-version={API_VERSION}
```

Where:
- `{endpoint}` is the Azure AI Search endpoint (trailing slash stripped)
- `{kb_name}` is the knowledge base name

## Required Imports

These are already imported at the top of `rag_client.py`:

```python
import os
import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework import MCPStreamableHTTPTool
```

## Function Signature

```python
def create_rag_mcp_tool(
    search_endpoint: str | None = None,
    knowledge_base_name: str | None = None,
    credential: DefaultAzureCredential | None = None,
) -> MCPStreamableHTTPTool:
```

### Parameters

- `search_endpoint` — Overrides `AZURE_SEARCH_ENDPOINT` env var
- `knowledge_base_name` — Overrides `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` env var
- `credential` — Overrides the default `DefaultAzureCredential()` instance

### Return Value

An `MCPStreamableHTTPTool` instance configured with:

| Property | Value |
|----------|-------|
| `name` | `"knowledge_base"` |
| `url` | The constructed MCP endpoint URL |
| `description` | A description of what the tool does (search company knowledge base for orders, products, shipping, policies) |
| `http_client` | An `httpx.AsyncClient` with `_AzureSearchAuth` for authentication |
| `approval_mode` | `"never_require"` |
| `load_prompts` | `False` |
| `parse_tool_results` | `_parse_mcp_rag_result` (the function already implemented in the file) |

## Implementation Steps

1. **Resolve endpoint:** Use the `search_endpoint` parameter if provided, otherwise read `AZURE_SEARCH_ENDPOINT` env var. Strip trailing slashes.
2. **Resolve knowledge base name:** Use the `knowledge_base_name` parameter if provided, otherwise read `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` env var (default: `customer-support-kb`).
3. **Build MCP URL:** `f"{endpoint}/knowledgebases/{kb_name}/mcp?api-version={API_VERSION}"`
4. **Create credential:** Use the `credential` parameter if provided, otherwise create `DefaultAzureCredential()`.
5. **Create auth:** Instantiate `_AzureSearchAuth(cred)`.
6. **Create HTTP client:** `httpx.AsyncClient(auth=auth)`.
7. **Create and return** `MCPStreamableHTTPTool` with all the properties above.

## Agent Tools Integration

After the tool is created, it must be registered in `agent_tools.py`:

### `all` property

The `all` property should include the MCP RAG tool:

```python
@property
def all(self) -> list:
    return [self.get_order_status, self.check_memory, self._rag_mcp_tool, self.update_user_profile]
```

### `for_rag_mode()` method

This method selects tools based on the RAG mode:

```python
def for_rag_mode(self, rag_mode: str) -> list:
    base = [self.get_order_status, self.check_memory, self.update_user_profile]
    if rag_mode == "agentic":
        return base + [self._rag_mcp_tool]
    elif rag_mode == "classic":
        return base + [self.do_classic_rag]
    return base  # "none"
```

## Prompt Template Integration

The prompt in `prompts/customer_support.j2` needs Jinja2 conditional blocks based on the `rag_mode` template variable. The prompt should:

1. **Describe the RAG tools** to the agent (what they search, when to use them)
2. **Provide a tool selection guide** so the agent picks the right tool
3. **Define citation rules** so the agent formats inline annotations

### Citation Format

```
【search_idx:ref_id†source_name】
```

Example: `【0:return-policy_0†return-policy】`

The citations array from the tool result contains `search_idx`, `ref_id`, and `source_name` for each citation. Every fact from the knowledge base must have at least one inline annotation.

## Server Lifecycle

The MCP tool requires explicit connection management:

- **Startup:** `await rag_mcp_tool.connect()` — establishes MCP session with Azure AI Search
- **Shutdown:** `await rag_mcp_tool.close()` — cleanly disconnects

These calls happen in the FastAPI `lifespan()` function in `server.py`. They are guarded with `if rag_mcp_tool is not None` so the app starts cleanly when the tool is not configured.
