# rag_client.py
"""
RAG Client — MCP-based agentic retrieval via Azure AI Search knowledge base.

Uses MCPStreamableHTTPTool from agent_framework to expose the knowledge base
as MCP tools that the LLM can call directly, replacing the old REST-based
retrieve API approach.
"""

from __future__ import annotations

import logging
import os

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework import MCPStreamableHTTPTool

logger = logging.getLogger("ag_ui.rag_client")

API_VERSION = "2025-11-01-Preview"


def _parse_mcp_rag_result(result) -> str:
    """Parse MCP tool result into {content, citations} JSON matching the classic RAG format.

    The Azure AI Search MCP server returns TextContent with a JSON array of
    {ref_id, content} objects.  We transform this into the same structure
    the frontend converter expects for the citation card UI.
    """
    import json as _json

    # Extract raw text from MCP CallToolResult
    parts: list[str] = []
    for item in result.content:
        if hasattr(item, "text"):
            parts.append(item.text)
    raw = "\n".join(parts)

    # Try to parse as JSON array of {ref_id, content}
    try:
        items = _json.loads(raw)
    except (_json.JSONDecodeError, TypeError):
        return _json.dumps({"content": raw, "citations": []})

    if not isinstance(items, list):
        return _json.dumps({"content": raw, "citations": []})

    text_parts: list[str] = []
    citations: list[dict] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        chunk = item.get("content", "")
        ref_id = str(item.get("ref_id", ""))
        if chunk:
            text_parts.append(chunk)
            source_name = _derive_source_name(chunk, ref_id)
            citations.append({
                "search_idx": i,
                "ref_id": ref_id,
                "source_name": source_name,
                "content": chunk[:300],
                "annotation": f"\u3010{i}:{ref_id}\u2020{source_name}\u3011",
            })

    return _json.dumps({
        "content": "\n\n".join(text_parts),
        "citations": citations,
    })


def _derive_source_name(chunk: str, ref_id: str) -> str:
    """Derive a short source label from document content or ref_id."""
    import re
    first_line = chunk.strip().split("\n", 1)[0]
    m = re.match(r"^([A-Z][^:]{2,40}):", first_line)
    if m:
        return m.group(1).strip()
    if ref_id:
        parts = str(ref_id).split("-")
        if len(parts) >= 3 and parts[0].lower() == "ord":
            order_num = "-".join(parts[:2]).upper()
            label = " ".join(p.capitalize() for p in parts[2:])
            return f"Order {order_num} {label}".strip()
        if len(parts) >= 2 and parts[0].lower() == "policy":
            label = " ".join(p.capitalize() for p in parts[1:])
            return f"Policy: {label}"
        return " ".join(p.capitalize() for p in parts)[:40]
    return f"Source {ref_id}"


class _AzureSearchAuth(httpx.Auth):
    """httpx auth that injects Azure AD Bearer tokens for Azure AI Search."""

    def __init__(self, credential: DefaultAzureCredential | None = None) -> None:
        self._token_provider = get_bearer_token_provider(
            credential or DefaultAzureCredential(),
            "https://search.azure.com/.default",
        )

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._token_provider()}"
        yield request


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
