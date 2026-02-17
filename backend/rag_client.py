# rag_client.py
"""
RAG Client — Calls Azure AI Search knowledge base retrieve API for
agentic retrieval (extractive data mode).

Uses direct REST calls with aiohttp + DefaultAzureCredential to avoid
depending on preview SDK versions in the production backend.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import aiohttp
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

logger = logging.getLogger("ag_ui.rag_client")


@dataclass
class RAGCitation:
    """A single citation from the knowledge base retrieve response."""
    content: str
    ref_id: str
    source_name: str


@dataclass
class RAGResult:
    """Result from the knowledge base retrieve API."""
    content: str
    citations: list[RAGCitation] = field(default_factory=list)


class RAGClient:
    """Client for Azure AI Search agentic retrieval (knowledge base retrieve API)."""

    API_VERSION = "2025-11-01-Preview"

    def __init__(
        self,
        search_endpoint: str | None = None,
        knowledge_base_name: str | None = None,
        credential: DefaultAzureCredential | None = None,
    ):
        self._endpoint = (search_endpoint or os.getenv("AZURE_SEARCH_ENDPOINT", "")).rstrip("/")
        self._kb_name = knowledge_base_name or os.getenv("AZURE_SEARCH_KNOWLEDGE_BASE_NAME", "customer-support-kb")
        self._credential = credential or DefaultAzureCredential()
        self._token_provider = get_bearer_token_provider(
            self._credential, "https://search.azure.com/.default"
        )

    async def retrieve(
        self,
        query: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> RAGResult:
        """
        Call the knowledge base retrieve API.

        Uses intents-based retrieval (required for minimal reasoning effort).

        Args:
            query: Natural language query
            conversation_history: Optional list of {"role": ..., "content": ...} messages
                (used to build additional intent context if provided)

        Returns:
            RAGResult with content and citations
        """
        url = (
            f"{self._endpoint}/knowledgebases/{self._kb_name}"
            f"/retrieve?api-version={self.API_VERSION}"
        )

        # Minimal reasoning mode requires intents, not messages
        intents = [{"type": "semantic", "search": query}]

        payload = {"intents": intents}

        token = self._token_provider()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        logger.info("RAG retrieve: kb=%s query=%s", self._kb_name, query[:100])

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("RAG retrieve failed: status=%d body=%s", resp.status, body[:500])
                    return RAGResult(content=f"Knowledge base query failed (HTTP {resp.status})")

                data = await resp.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict) -> RAGResult:
        """Parse the knowledge base retrieve API response.

        The response text is a JSON array of {ref_id, content} objects.
        We flatten them into a single content string with citations.
        """
        import json as _json

        response_list = data.get("response", [])
        citations: list[RAGCitation] = []
        text_parts: list[str] = []
        seen_ref_ids: set[str] = set()

        for resp_item in response_list:
            if not isinstance(resp_item, dict):
                continue
            for content_part in resp_item.get("content", []):
                if not isinstance(content_part, dict) or content_part.get("type") != "text":
                    continue
                raw = content_part.get("text", "")
                if not raw or raw == "[]":
                    continue

                # The text is a JSON array of {ref_id, content} objects
                try:
                    items = _json.loads(raw)
                    if isinstance(items, list):
                        for item in items:
                            chunk = item.get("content", "")
                            ref_id = str(item.get("ref_id", ""))
                            if chunk:
                                text_parts.append(chunk)
                                if ref_id and ref_id not in seen_ref_ids:
                                    seen_ref_ids.add(ref_id)
                                    # Derive a short source label from the content
                                    source_name = self._derive_source_name(chunk, ref_id)
                                    citations.append(
                                        RAGCitation(
                                            content=chunk[:300],
                                            ref_id=ref_id,
                                            source_name=source_name,
                                        )
                                    )
                    else:
                        text_parts.append(raw)
                except (_json.JSONDecodeError, TypeError):
                    text_parts.append(raw)

        content = "\n\n".join(text_parts)
        logger.info("RAG result: content_len=%d citations=%d", len(content), len(citations))
        return RAGResult(content=content, citations=citations)

    @staticmethod
    def _derive_source_name(chunk: str, ref_id: str) -> str:
        """Derive a short, meaningful source label from document content.

        Strategy:
        1. If the chunk starts with a title pattern like "Some Title:", use that.
        2. Otherwise fall back to a cleaned-up version of the ref_id.
        """
        import re

        # Check for "Title:" pattern at the start of the content
        first_line = chunk.strip().split("\n", 1)[0]
        m = re.match(r"^([A-Z][^:]{2,40}):", first_line)
        if m:
            return m.group(1).strip()

        # Fall back to humanised ref_id  (e.g. "ord-001-shipping" → "Order ORD-001 Shipping")
        if ref_id:
            parts = ref_id.split("-")
            # Handle order-style IDs like "ord-001-shipping"
            if len(parts) >= 3 and parts[0].lower() == "ord":
                order_num = "-".join(parts[:2]).upper()
                label = " ".join(p.capitalize() for p in parts[2:])
                return f"Order {order_num} {label}".strip()
            # Handle policy-style IDs like "policy-eligibility"
            if len(parts) >= 2 and parts[0].lower() == "policy":
                label = " ".join(p.capitalize() for p in parts[1:])
                return f"Policy: {label}"
            # Generic fallback: capitalize parts
            return " ".join(p.capitalize() for p in parts)[:40]

        return f"Source {ref_id}"
