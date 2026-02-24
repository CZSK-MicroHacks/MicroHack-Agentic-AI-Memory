"""
Hybrid search (semantic + keyword) on the nodes table.

Provides:
- semantic_search: cosine similarity on embeddings
- keyword_search: PostgreSQL full-text search on tsvector
- hybrid_search: Reciprocal Rank Fusion combining both
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from .db import get_pool

logger = logging.getLogger("kg.search")


async def semantic_search(
    query_embedding: list[float],
    *,
    node_type: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Vector cosine similarity search on the nodes table."""
    pool = await get_pool()
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    if node_type:
        rows = await pool.fetch(
            """
            SELECT id, node_type, name, description, properties,
                   1 - (embedding <=> $1::vector) AS score
            FROM nodes
            WHERE node_type = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            embedding_str, node_type, limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, node_type, name, description, properties,
                   1 - (embedding <=> $1::vector) AS score
            FROM nodes
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            embedding_str, limit,
        )
    return [dict(r) for r in rows]


async def keyword_search(
    query: str,
    *,
    node_type: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Full-text search using tsvector/tsquery."""
    pool = await get_pool()
    tsquery = " & ".join(query.strip().split())

    if node_type:
        rows = await pool.fetch(
            """
            SELECT id, node_type, name, description, properties,
                   ts_rank(search_text, to_tsquery('english', $1)) AS score
            FROM nodes
            WHERE search_text @@ to_tsquery('english', $1)
              AND node_type = $2
            ORDER BY score DESC
            LIMIT $3
            """,
            tsquery, node_type, limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, node_type, name, description, properties,
                   ts_rank(search_text, to_tsquery('english', $1)) AS score
            FROM nodes
            WHERE search_text @@ to_tsquery('english', $1)
            ORDER BY score DESC
            LIMIT $2
            """,
            tsquery, limit,
        )
    return [dict(r) for r in rows]


async def hybrid_search(
    query: str,
    query_embedding: list[float],
    *,
    node_type: str | None = None,
    limit: int = 10,
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> list[dict[str, Any]]:
    """
    Reciprocal Rank Fusion combining semantic and keyword search.

    Each result gets: rrf_score = w_sem / (k + rank_sem) + w_kw / (k + rank_kw)
    where k=60 (standard RRF constant).
    """
    k = 60  # RRF smoothing constant
    fetch_limit = limit * 3  # Over-fetch for better fusion

    sem_results = await semantic_search(query_embedding, node_type=node_type, limit=fetch_limit)
    kw_results = await keyword_search(query, node_type=node_type, limit=fetch_limit)

    # Build rank maps (1-indexed)
    sem_ranks: dict[str, int] = {}
    for i, r in enumerate(sem_results, 1):
        sem_ranks[str(r["id"])] = i

    kw_ranks: dict[str, int] = {}
    for i, r in enumerate(kw_results, 1):
        kw_ranks[str(r["id"])] = i

    # Merge all candidate IDs
    all_ids = set(sem_ranks.keys()) | set(kw_ranks.keys())

    # Build result lookup
    result_map: dict[str, dict] = {}
    for r in sem_results + kw_results:
        rid = str(r["id"])
        if rid not in result_map:
            result_map[rid] = r

    # Compute RRF scores
    scored = []
    for rid in all_ids:
        sem_rank = sem_ranks.get(rid, fetch_limit + 1)
        kw_rank = kw_ranks.get(rid, fetch_limit + 1)
        rrf = (semantic_weight / (k + sem_rank)) + (keyword_weight / (k + kw_rank))
        entry = dict(result_map[rid])
        entry["rrf_score"] = rrf
        entry["semantic_rank"] = sem_rank if rid in sem_ranks else None
        entry["keyword_rank"] = kw_rank if rid in kw_ranks else None
        scored.append(entry)

    scored.sort(key=lambda x: x["rrf_score"], reverse=True)
    return scored[:limit]
