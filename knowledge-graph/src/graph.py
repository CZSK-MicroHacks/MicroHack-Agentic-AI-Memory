"""
Graph traversal using Apache AGE Cypher queries.

Provides functions for:
- get_neighbors: direct connections from a node
- find_shared_connections: common neighbors between two nodes
- expand_community: all members of a concept/community
- find_path: shortest path between two nodes
- find_similar_by_relationships: nodes sharing the most connections
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from .db import get_pool

logger = logging.getLogger("kg.graph")


def _escape(s: str) -> str:
    """Escape single quotes for Cypher strings."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


async def _cypher(pool: asyncpg.Pool, query: str, return_cols: str) -> list[asyncpg.Record]:
    """Execute a Cypher query through AGE's SQL wrapper."""
    sql = f"""
        SELECT * FROM cypher('biomedical', $$ {query} $$) AS ({return_cols});
    """
    async with pool.acquire() as conn:
        await conn.execute('SET search_path = ag_catalog, "$user", public;')
        return await conn.fetch(sql)


def _parse_agtype(val: Any) -> Any:
    """Parse an agtype value into a Python object."""
    if val is None:
        return None
    s = str(val)
    # agtype strings are quoted with double quotes
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    # Try JSON parse for objects/arrays
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s


async def get_neighbors(
    node_name: str,
    *,
    relationship_type: str | None = None,
    direction: str = "both",
    depth: int = 1,
) -> list[dict[str, Any]]:
    """
    Get neighbors of a node, optionally filtered by relationship type.

    Args:
        node_name: Name of the starting node
        relationship_type: Filter by edge type (e.g. "TREATS", "INTERACTS_WITH")
        direction: "out", "in", or "both"
        depth: How many hops (1 = direct neighbors, 2 = two hops)
    """
    pool = await get_pool()
    name = _escape(node_name)

    # Build relationship pattern
    rel_filter = f":{relationship_type}" if relationship_type else ""

    if depth > 1:
        # Variable-length paths: label() doesn't work on path edges
        depth_str = f"*1..{depth}"
        if direction == "out":
            pattern = f"(a {{name: '{name}'}})-[{rel_filter}{depth_str}]->(b)"
        elif direction == "in":
            pattern = f"(a {{name: '{name}'}})<-[{rel_filter}{depth_str}]-(b)"
        else:
            pattern = f"(a {{name: '{name}'}})-[{rel_filter}{depth_str}]-(b)"

        cypher = f"MATCH {pattern} WHERE a <> b RETURN DISTINCT b.name"
        rows = await _cypher(pool, cypher, "name agtype")
        return [{"name": _parse_agtype(row["name"]), "relationship_type": "multi_hop", "properties": {}} for row in rows]

    # Single-hop: can use label(r) and return edge properties
    if direction == "out":
        pattern = f"(a {{name: '{name}'}})-[r{rel_filter}]->(b)"
    elif direction == "in":
        pattern = f"(a {{name: '{name}'}})<-[r{rel_filter}]-(b)"
    else:
        pattern = f"(a {{name: '{name}'}})-[r{rel_filter}]-(b)"

    cypher = f"MATCH {pattern} RETURN DISTINCT b.name, label(r), r"
    rows = await _cypher(pool, cypher, "name agtype, rel_type agtype, rel_props agtype")

    results = []
    for row in rows:
        results.append({
            "name": _parse_agtype(row["name"]),
            "relationship_type": _parse_agtype(row["rel_type"]),
            "properties": _parse_agtype(row["rel_props"]),
        })
    return results


async def find_shared_connections(
    node_name_1: str,
    node_name_2: str,
) -> dict[str, Any]:
    """
    Find what two nodes have in common: shared neighbors, shared communities, shared paths.
    """
    pool = await get_pool()
    n1 = _escape(node_name_1)
    n2 = _escape(node_name_2)

    # Shared direct neighbors
    cypher = (
        f"MATCH (a {{name: '{n1}'}})-[r1]-(shared)-[r2]-(b {{name: '{n2}'}}) "
        f"WHERE a <> b AND a <> shared AND b <> shared "
        f"RETURN DISTINCT shared.name, label(r1), label(r2)"
    )
    rows = await _cypher(pool, cypher, "shared agtype, r1_type agtype, r2_type agtype")

    shared = []
    for row in rows:
        shared.append({
            "shared_node": _parse_agtype(row["shared"]),
            "relationship_to_first": _parse_agtype(row["r1_type"]),
            "relationship_to_second": _parse_agtype(row["r2_type"]),
        })

    # Shared communities
    cypher = (
        f"MATCH (a {{name: '{n1}'}})-[:BELONGS_TO_COMMUNITY]->(c)<-[:BELONGS_TO_COMMUNITY]-(b {{name: '{n2}'}}) "
        f"RETURN DISTINCT c.name"
    )
    rows = await _cypher(pool, cypher, "community agtype")
    shared_communities = [_parse_agtype(r["community"]) for r in rows]

    return {
        "node_1": node_name_1,
        "node_2": node_name_2,
        "shared_neighbors": shared,
        "shared_communities": shared_communities,
    }


async def expand_community(concept_name: str) -> dict[str, Any]:
    """
    BFS expansion: get all members of a concept/community node.
    Returns the concept description and all member nodes.
    """
    pool = await get_pool()
    name = _escape(concept_name)

    # Get concept description from nodes table
    async with pool.acquire() as conn:
        concept = await conn.fetchrow(
            "SELECT name, description FROM nodes WHERE node_type = 'concept' AND name = $1",
            concept_name,
        )

    if not concept:
        return {"error": f"Concept '{concept_name}' not found"}

    # Get all members via graph
    cypher = (
        f"MATCH (member)-[:BELONGS_TO_COMMUNITY]->(c {{name: '{name}'}}) "
        f"RETURN member.name, member.node_id"
    )
    rows = await _cypher(pool, cypher, "name agtype, node_id agtype")

    members = []
    for row in rows:
        members.append({
            "name": _parse_agtype(row["name"]),
            "node_id": _parse_agtype(row["node_id"]),
        })

    # Get inter-member relationships
    cypher = (
        f"MATCH (a)-[:BELONGS_TO_COMMUNITY]->(c {{name: '{name}'}}), "
        f"(b)-[:BELONGS_TO_COMMUNITY]->(c), "
        f"(a)-[r]->(b) "
        f"WHERE a <> b AND NOT label(r) = 'BELONGS_TO_COMMUNITY' "
        f"RETURN a.name, label(r), b.name"
    )
    rows = await _cypher(pool, cypher, "source agtype, rel agtype, target agtype")

    internal_rels = []
    for row in rows:
        internal_rels.append({
            "source": _parse_agtype(row["source"]),
            "relationship": _parse_agtype(row["rel"]),
            "target": _parse_agtype(row["target"]),
        })

    return {
        "concept": concept_name,
        "description": concept["description"],
        "members": members,
        "internal_relationships": internal_rels,
    }


async def find_similar_by_graph(
    node_name: str,
    *,
    strategy: str = "shared_neighbors",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Find nodes most similar to a given node based on graph structure.

    Strategies:
    - "shared_neighbors": nodes sharing the most direct neighbors
    - "shared_communities": nodes sharing the most community memberships
    """
    pool = await get_pool()
    name = _escape(node_name)

    if strategy == "shared_neighbors":
        cypher = (
            f"MATCH (a {{name: '{name}'}})-[]-(shared)-[]-(b) "
            f"WHERE a <> b AND a <> shared AND b <> shared "
            f"RETURN b.name, count(DISTINCT shared) "
            f"ORDER BY count(DISTINCT shared) DESC "
            f"LIMIT {limit}"
        )
        rows = await _cypher(pool, cypher, "name agtype, cnt agtype")
        return [
            {"name": _parse_agtype(r["name"]), "shared_count": _parse_agtype(r["cnt"])}
            for r in rows
        ]

    elif strategy == "shared_communities":
        cypher = (
            f"MATCH (a {{name: '{name}'}})-[:BELONGS_TO_COMMUNITY]->(c)<-[:BELONGS_TO_COMMUNITY]-(b) "
            f"WHERE a <> b "
            f"RETURN b.name, count(DISTINCT c) "
            f"ORDER BY count(DISTINCT c) DESC "
            f"LIMIT {limit}"
        )
        rows = await _cypher(pool, cypher, "name agtype, cnt agtype")
        return [
            {"name": _parse_agtype(r["name"]), "shared_count": _parse_agtype(r["cnt"])}
            for r in rows
        ]

    return []
