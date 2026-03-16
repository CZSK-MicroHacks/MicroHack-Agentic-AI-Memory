# Solution 05 — Knowledge Base (RAG via Azure AI Search)

This solution enables RAG (Retrieval-Augmented Generation) by connecting the agent to Azure AI Search via MCP.

## Part 1: `create_rag_mcp_tool()` in `rag_client.py`

Replace the stubbed `create_rag_mcp_tool()` function with:

```python
def create_rag_mcp_tool(
    search_endpoint: str | None = None,
    knowledge_base_name: str | None = None,
    credential: DefaultAzureCredential | None = None,
) -> MCPStreamableHTTPTool:
    """Create an MCPStreamableHTTPTool for Azure AI Search agentic retrieval.

    The returned tool must be used as an async context manager (``async with``)
    to establish the MCP connection before it is passed to an Agent.

    Args:
        search_endpoint: Azure AI Search endpoint URL (falls back to
            ``AZURE_SEARCH_ENDPOINT`` env var).
        knowledge_base_name: Knowledge base name (falls back to
            ``AZURE_SEARCH_KNOWLEDGE_BASE_NAME`` env var).
        credential: Azure credential for token acquisition.

    Returns:
        An MCPStreamableHTTPTool ready to be connected.
    """
    endpoint = (search_endpoint or os.getenv("AZURE_SEARCH_ENDPOINT", "")).rstrip("/")
    kb_name = knowledge_base_name or os.getenv(
        "AZURE_SEARCH_KNOWLEDGE_BASE_NAME", "customer-support-kb"
    )

    url = f"{endpoint}/knowledgebases/{kb_name}/mcp?api-version={API_VERSION}"

    cred = credential or DefaultAzureCredential()
    auth = _AzureSearchAuth(cred)
    http_client = httpx.AsyncClient(auth=auth)

    logger.info("Creating MCP RAG tool: url=%s", url)

    return MCPStreamableHTTPTool(
        name="knowledge_base",
        url=url,
        description=(
            "Search the company knowledge base for detailed information "
            "about orders, products, shipping, and return/refund policies."
        ),
        http_client=http_client,
        approval_mode="never_require",
        load_prompts=False,
        parse_tool_results=_parse_mcp_rag_result,
    )
```

## Part 2: Register RAG tools in `agent_tools.py`

### Update the `all` property

```python
@property
def all(self) -> list:
    """All tools including agentic RAG via MCP."""
    return [self.get_order_status, self.check_memory, self._rag_mcp_tool, self.update_user_profile]
```

### Update `for_rag_mode()` method

```python
def for_rag_mode(self, rag_mode: str) -> list:
    """Return tool list for the given RAG mode."""
    base = [self.get_order_status, self.check_memory, self.update_user_profile]
    if rag_mode == "agentic":
        return base + [self._rag_mcp_tool]
    elif rag_mode == "classic":
        return base + [self.do_classic_rag]
    return base  # "none"
```

## Part 3: Prompt template `prompts/customer_support.j2`

Add the following blocks after the `check_memory` paragraph (after line 14). These add conditional RAG tool instructions and citation rules:

```jinja2
{%- if rag_mode is not defined or rag_mode == 'agentic' %}
You also have access to knowledge base tools provided via MCP (Model Context Protocol)
that search the company knowledge base using agentic retrieval (AI-driven reasoning
across multiple knowledge sources — orders and policies). Use the knowledge base tools
when the user asks about:
- Detailed product descriptions, specifications, or features
- Shipping details (carrier, weight, packaging, dimensions)
- Return policy rules, eligibility windows, or refund timelines
- Refund methods, processing times, or exceptions
- Any detailed information beyond a simple order status check
{%- elif rag_mode == 'classic' %}
You also have access to a do_classic_rag tool that searches the orders knowledge
base using classic hybrid search (keyword + vector + semantic ranking). This tool
searches ONLY the orders index. Use do_classic_rag when the user asks about:
- Detailed product descriptions, specifications, or features
- Shipping details (carrier, weight, packaging, dimensions)
- Any order-specific information beyond the basic status

NOTE: This tool does NOT cover return/refund policies. If the user asks about
policies, inform them that classic search does not cover policy documents and
suggest they enable agentic RAG for that.
{%- endif %}
```

Update the **TOOL SELECTION GUIDE** section to include RAG entries:

```jinja2
TOOL SELECTION GUIDE:
- For "What's the status of my order?" → use get_order_status
{%- if rag_mode is not defined or rag_mode == 'agentic' %}
- For "What products were in my order?" → use the knowledge base tools
- For "What is your return policy?" → use the knowledge base tools
- For "Can I return my order?" → use knowledge base tools (to check policy) then get_order_status (for dates)
{%- elif rag_mode == 'classic' %}
- For "What products were in my order?" → use do_classic_rag
- For "What is your return policy?" → NOT available via classic search
{%- endif %}
- For "What did we talk about last time?" → use check_memory
```

Add **citation/annotation rules** block:

```jinja2
{%- set _rag_tool = 'do_classic_rag' if (rag_mode is defined and rag_mode == 'classic') else 'knowledge base' %}

{%- if rag_mode is not defined or rag_mode in ['agentic', 'classic'] %}
CITATION / ANNOTATION RULES ({{ _rag_tool }} results):
When using information from {{ _rag_tool }}, you MUST include inline annotations in
your response. The {{ _rag_tool }} tool returns a "citations" array; each citation has
a "search_idx", "ref_id", and "source_name". For every fact you use from the
knowledge base, append an annotation in this exact format:

  【search_idx:ref_id†source_name】

For example, if the tool returns a citation with search_idx=0, ref_id="return-policy_0",
source_name="return-policy", write your sentence followed by 【0:return-policy_0†return-policy】

Rules:
- Every claim sourced from the knowledge base MUST have at least one annotation.
- Place annotations immediately after the relevant sentence or phrase.
- You may cite multiple sources for a single statement.
- If no citations were returned, do not fabricate annotations.

When presenting information from {{ _rag_tool }}, incorporate it naturally into your
response. Do not dump raw citation data to the user — use the annotations.
{%- endif %}
```

## Part 4: Server lifecycle (`server.py`)

No changes needed — the `lifespan()` function already guards MCP connection with `if rag_mcp_tool is not None`. Once Part 1 returns a real tool, the connection is established automatically.

## Key Concepts

- **Agentic RAG vs Classic RAG:** Agentic RAG uses MCP to let the AI reason across multiple knowledge sources (orders + policies). Classic RAG searches a single pre-configured index using keyword + vector + semantic ranking.
- **MCP (Model Context Protocol):** A standard for exposing tools to LLMs. Azure AI Search's knowledge base retrieve API exposes an MCP endpoint that the agent can call.
- **Citation annotations:** The `【idx:ref†source】` format is parsed by the frontend to render clickable citation cards.
- **`_parse_mcp_rag_result`:** Converts MCP's raw `{ref_id, content}` arrays into the `{content, citations}` format the frontend expects.
