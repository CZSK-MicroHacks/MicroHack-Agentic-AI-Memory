# classic_rag_client.py
"""
Classic RAG Client — Standard hybrid search (text + vector + semantic ranking)
against a single Azure AI Search index.

This contrasts with the agentic RAG path (rag_client.py) which uses the
knowledge base retrieve API with AI-driven reasoning across multiple indexes.

The classic path deliberately searches only the "orders" index to showcase
the difference: agentic RAG can span multiple knowledge sources intelligently,
while classic RAG hits a single pre-configured index.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import aiohttp
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

logger = logging.getLogger("ag_ui.classic_rag_client")


@dataclass
class ClassicRAGCitation:
    """A single citation from the hybrid search response."""
    content: str
    ref_id: str
    source_name: str


@dataclass
class ClassicRAGResult:
    """Result from the classic hybrid search."""
    content: str
    citations: list[ClassicRAGCitation] = field(default_factory=list)


class ClassicRAGClient:
    """Client for Azure AI Search standard hybrid search (text + vector + semantic)."""

    API_VERSION = "2024-07-01"

    def __init__(
        self,
        search_endpoint: str | None = None,
        index_name: str | None = None,
        credential: DefaultAzureCredential | None = None,
    ):
        self._endpoint = (search_endpoint or os.getenv("AZURE_SEARCH_ENDPOINT", "")).rstrip("/")
        self._index_name = index_name or os.getenv("AZURE_SEARCH_ORDERS_INDEX", "orders")
        self._credential = credential or DefaultAzureCredential()
        self._token_provider = get_bearer_token_provider(
            self._credential, "https://search.azure.com/.default"
        )

    async def search(self, query: str, top: int = 5) -> ClassicRAGResult:
        """
        Execute a hybrid search (keyword + vector via integrated vectorizer + semantic ranking).

        Retries on 502 errors (common during integrated vectorizer cold start).

        Args:
            query: Natural language query
            top: Maximum number of results to return

        Returns:
            ClassicRAGResult with content and citations
        """
        import asyncio

        url = (
            f"{self._endpoint}/indexes/{self._index_name}"
            f"/docs/search?api-version={self.API_VERSION}"
        )

        payload = {
            "search": query,
            "vectorQueries": [
                {
                    "kind": "text",
                    "text": query,
                    "fields": "page_embedding",
                    "k": top,
                }
            ],
            "queryType": "semantic",
            "semanticConfiguration": "semantic_config",
            "select": "id, order_id, category, page_chunk",
            "top": top,
        }

        logger.info("Classic RAG search: index=%s query=%s top=%d", self._index_name, query[:100], top)

        max_retries = 3
        for attempt in range(max_retries):
            token = self._token_provider()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._parse_response(data)

                    body = await resp.text()
                    if resp.status == 502 and attempt < max_retries - 1:
                        wait = 2 ** attempt
                        logger.warning(
                            "Classic RAG search got 502 (attempt %d/%d), retrying in %ds…",
                            attempt + 1, max_retries, wait,
                        )
                        await asyncio.sleep(wait)
                        continue

                    logger.error("Classic RAG search failed: status=%d body=%s", resp.status, body[:500])
                    return ClassicRAGResult(content=f"Search failed (HTTP {resp.status})")

        return ClassicRAGResult(content="Search failed after retries")

    def _parse_response(self, data: dict) -> ClassicRAGResult:
        """Parse the standard search response into content + citations."""
        results = data.get("value", [])
        citations: list[ClassicRAGCitation] = []
        text_parts: list[str] = []

        for doc in results:
            chunk = doc.get("page_chunk", "")
            doc_id = doc.get("id", "")
            if not chunk:
                continue

            text_parts.append(chunk)
            source_name = self._derive_source_name(chunk, doc_id)
            citations.append(
                ClassicRAGCitation(
                    content=chunk[:300],
                    ref_id=doc_id,
                    source_name=source_name,
                )
            )

        content = "\n\n".join(text_parts)
        logger.info("Classic RAG result: content_len=%d citations=%d", len(content), len(citations))
        return ClassicRAGResult(content=content, citations=citations)

    @staticmethod
    def _derive_source_name(chunk: str, ref_id: str) -> str:
        """Derive a short, meaningful source label from document content.

        Same logic as RAGClient._derive_source_name for consistency.
        """
        import re

        first_line = chunk.strip().split("\n", 1)[0]
        m = re.match(r"^([A-Z][^:]{2,40}):", first_line)
        if m:
            return m.group(1).strip()

        if ref_id:
            parts = ref_id.split("-")
            if len(parts) >= 3 and parts[0].lower() == "ord":
                order_num = "-".join(parts[:2]).upper()
                label = " ".join(p.capitalize() for p in parts[2:])
                return f"Order {order_num} {label}".strip()
            if len(parts) >= 2 and parts[0].lower() == "policy":
                label = " ".join(p.capitalize() for p in parts[1:])
                return f"Policy: {label}"
            return " ".join(p.capitalize() for p in parts)[:40]

        return f"Source {ref_id}"
