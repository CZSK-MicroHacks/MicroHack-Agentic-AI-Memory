"""
Agent tools for knowledge graph search and traversal.

These tools wrap the search and graph modules to provide agent-callable functions.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import AzureOpenAI

from .search import hybrid_search, semantic_search, keyword_search
from .graph import (
    get_neighbors,
    find_shared_connections,
    expand_community,
    find_similar_by_graph,
)

logger = logging.getLogger("kg.tools")

_client: AzureOpenAI | None = None


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        from dotenv import load_dotenv
        load_dotenv()
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if api_key:
            _client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
            _client = AzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=token_provider, api_version=api_version)
    return _client


def _embed(text: str) -> list[float]:
    """Compute embedding for a single text."""
    deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large")
    resp = _get_client().embeddings.create(model=deployment, input=[text], dimensions=1536)
    return resp.data[0].embedding


async def search_entities(
    query: str,
    node_type: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Search entity nodes using hybrid search (semantic + keyword).

    Use this as the starting point for depth-first exploration.
    Optionally filter by node_type: drug, disease, gene, symptom, pathway.
    """
    logger.info("search_entities: query=%s, node_type=%s", query, node_type)
    embedding = _embed(query)

    # Exclude concept nodes unless explicitly asked
    if node_type is None:
        results = await hybrid_search(query, embedding, limit=limit)
        results = [r for r in results if r["node_type"] != "concept"]
    else:
        results = await hybrid_search(query, embedding, node_type=node_type, limit=limit)

    return [
        {
            "id": str(r["id"]),
            "node_type": r["node_type"],
            "name": r["name"],
            "description": r["description"],
            "score": round(r.get("rrf_score", 0), 4),
        }
        for r in results[:limit]
    ]


async def search_concepts(
    query: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """
    Search concept/community nodes using hybrid search.

    Use this as the starting point for breadth-first exploration of therapeutic areas.
    """
    logger.info("search_concepts: query=%s", query)
    embedding = _embed(query)
    results = await hybrid_search(query, embedding, node_type="concept", limit=limit)
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "description": r["description"],
            "score": round(r.get("rrf_score", 0), 4),
        }
        for r in results
    ]


async def find_related(
    node_name: str,
    relationship_type: str | None = None,
    depth: int = 1,
) -> list[dict[str, Any]]:
    """
    Graph traversal: find nodes connected to a given node (DFS).

    Args:
        node_name: Exact name of the starting node
        relationship_type: Optional filter (e.g. "TREATS", "INTERACTS_WITH", "CAUSES_SIDE_EFFECT")
        depth: Number of hops (1=direct, 2=two hops for indirect connections)
    """
    logger.info("find_related: node=%s, rel=%s, depth=%d", node_name, relationship_type, depth)
    return await get_neighbors(node_name, relationship_type=relationship_type, depth=depth)


async def tool_expand_concept(concept_name: str) -> dict[str, Any]:
    """
    BFS expansion: get all members and internal relationships of a concept/community.

    Use after search_concepts to explore a therapeutic area in detail.
    """
    logger.info("expand_concept: %s", concept_name)
    return await expand_community(concept_name)


async def tool_find_shared_connections(
    node_name_1: str,
    node_name_2: str,
) -> dict[str, Any]:
    """
    Find what two nodes have in common: shared neighbors, shared communities.

    Useful for discovering non-obvious relationships between entities.
    """
    logger.info("find_shared_connections: %s <-> %s", node_name_1, node_name_2)
    return await find_shared_connections(node_name_1, node_name_2)


async def tool_find_similar_by_graph(
    node_name: str,
    strategy: str = "shared_neighbors",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Find nodes structurally similar to a given node in the graph.

    Strategies:
    - "shared_neighbors": nodes sharing the most direct connections
    - "shared_communities": nodes in the most overlapping communities
    """
    logger.info("find_similar: node=%s, strategy=%s", node_name, strategy)
    return await find_similar_by_graph(node_name, strategy=strategy, limit=limit)
