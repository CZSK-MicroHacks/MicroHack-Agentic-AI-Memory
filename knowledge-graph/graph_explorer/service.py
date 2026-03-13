from __future__ import annotations

import asyncio
import json
import os
import re
import ssl
from collections import deque
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")
load_dotenv()

MAX_NEIGHBORHOOD_DEPTH = 3
MAX_PATH_DEPTH = 5
MAX_GRAPH_NODES = 60
RELATIONSHIP_RE = re.compile(r"[A-Z][A-Z0-9_]*")

_pool: asyncpg.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


def _create_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


async def get_pool() -> asyncpg.Pool:
    global _pool, _pool_loop

    loop = asyncio.get_running_loop()
    if _pool is not None and _pool_loop is not loop:
        _pool = None
        _pool_loop = None

    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.getenv("PG_HOST", "localhost"),
            port=int(os.getenv("PG_PORT", "5432")),
            user=os.getenv("PG_USER", "pgadmin"),
            password=os.getenv("PG_PASSWORD", ""),
            database=os.getenv("PG_DATABASE", "appdb"),
            ssl=_create_ssl_context(),
            min_size=1,
            max_size=5,
        )
        _pool_loop = loop
    return _pool


async def close_pool() -> None:
    global _pool, _pool_loop
    if _pool is not None:
        await _pool.close()
        _pool = None
        _pool_loop = None


def _escape_cypher_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _parse_agtype(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _validate_relationship_type(relationship_type: str | None) -> str | None:
    if not relationship_type:
        return None
    normalized = relationship_type.strip().upper()
    if not RELATIONSHIP_RE.fullmatch(normalized):
        raise ValueError("Relationship type must contain only letters, numbers, and underscores.")
    return normalized


async def _cypher(query: str, return_cols: str) -> list[asyncpg.Record]:
    pool = await get_pool()
    sql = f"""
        SELECT * FROM cypher('biomedical', $$ {query} $$) AS ({return_cols});
    """
    async with pool.acquire() as conn:
        await conn.execute('SET search_path = ag_catalog, "$user", public;')
        return await conn.fetch(sql)


async def _fetch_node_records(names: list[str]) -> dict[str, dict[str, Any]]:
    if not names:
        return {}

    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT name, node_type, description, properties
        FROM nodes
        WHERE name = ANY($1::text[])
        ORDER BY name, node_type
        """,
        names,
    )

    records: dict[str, dict[str, Any]] = {}
    for row in rows:
        records.setdefault(
            row["name"],
            {
                "name": row["name"],
                "node_type": row["node_type"],
                "description": row["description"],
                "properties": row["properties"] or {},
            },
        )
    return records


async def list_relationship_types() -> list[str]:
    query = "MATCH ()-[r]->() RETURN DISTINCT label(r) AS rel_type"
    rows = await _cypher(query, "rel_type agtype")
    return sorted(_parse_agtype(row["rel_type"]) for row in rows)


async def sample_nodes(per_type: int = 2) -> list[dict[str, str]]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT node_type, name
        FROM (
            SELECT node_type, name,
                   row_number() OVER (PARTITION BY node_type ORDER BY name) AS rn
            FROM nodes
            WHERE node_type <> 'concept'
        ) ranked
        WHERE rn <= $1
        ORDER BY node_type, name
        """,
        per_type,
    )
    return [{"node_type": row["node_type"], "name": row["name"]} for row in rows]


async def search_nodes(query: str, limit: int = 12) -> list[dict[str, Any]]:
    term = query.strip()
    if not term:
        return []

    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (name) name, node_type, description
        FROM nodes
        WHERE name ILIKE $1 OR description ILIKE $1
        ORDER BY name,
                 CASE
                     WHEN lower(name) = lower($2) THEN 0
                     WHEN name ILIKE $3 THEN 1
                     ELSE 2
                 END,
                 char_length(name)
        LIMIT $4
        """,
        f"%{term}%",
        term,
        f"{term}%",
        limit,
    )
    return [dict(row) for row in rows]


async def get_node_details(name: str) -> dict[str, Any] | None:
    records = await _fetch_node_records([name])
    details = records.get(name)
    if details is None:
        return None

    escaped_name = _escape_cypher_literal(name)
    community_query = (
        f"MATCH (n {{name: '{escaped_name}'}})-[:BELONGS_TO_COMMUNITY]->(c) "
        f"RETURN DISTINCT c.name AS community"
    )
    rows = await _cypher(community_query, "community agtype")
    details["communities"] = sorted(_parse_agtype(row["community"]) for row in rows)
    details["cypher_queries"] = [community_query]
    return details


async def _fetch_connected_edges(
    node_name: str,
    relationship_type: str | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    escaped_name = _escape_cypher_literal(node_name)
    rel_filter = f":{relationship_type}" if relationship_type else ""
    outgoing = (
        f"MATCH (a {{name: '{escaped_name}'}})-[r{rel_filter}]->(b) "
        f"RETURN a.name AS source, label(r) AS rel_type, b.name AS target"
    )
    incoming = (
        f"MATCH (a {{name: '{escaped_name}'}})<-[r{rel_filter}]-(b) "
        f"RETURN b.name AS source, label(r) AS rel_type, a.name AS target"
    )
    combined = f"{outgoing} UNION {incoming}"
    rows = await _cypher(combined, "source agtype, rel_type agtype, target agtype")
    edges = [
        {
            "source": _parse_agtype(row["source"]),
            "relationship_type": _parse_agtype(row["rel_type"]),
            "target": _parse_agtype(row["target"]),
        }
        for row in rows
    ]
    return edges, [outgoing, incoming]


def _edge_id(source: str, relationship_type: str, target: str) -> str:
    return f"{source}|{relationship_type}|{target}"


def _build_node_payload(
    name: str,
    metadata: dict[str, Any] | None,
    *,
    is_focus: bool = False,
    is_path: bool = False,
) -> dict[str, Any]:
    metadata = metadata or {}
    description = metadata.get("description") or ""
    node_type = metadata.get("node_type") or "unknown"
    properties = metadata.get("properties") or {}
    return {
        "id": name,
        "label": name,
        "name": name,
        "node_type": node_type,
        "description": description,
        "properties": properties,
        "is_focus": is_focus,
        "is_path": is_path,
    }


async def build_neighborhood_graph(
    node_name: str,
    *,
    relationship_type: str | None = None,
    depth: int = 1,
    max_nodes: int = MAX_GRAPH_NODES,
) -> dict[str, Any]:
    relationship_type = _validate_relationship_type(relationship_type)
    depth = max(1, min(depth, MAX_NEIGHBORHOOD_DEPTH))
    max_nodes = max(5, min(max_nodes, MAX_GRAPH_NODES))

    focus_details = await get_node_details(node_name)
    if focus_details is None:
        raise ValueError(f"Node '{node_name}' was not found.")

    visited: set[str] = {node_name}
    frontier = [node_name]
    edge_map: dict[str, dict[str, Any]] = {}
    cypher_queries: list[str] = list(focus_details.get("cypher_queries", []))

    for _ in range(depth):
        if not frontier or len(visited) >= max_nodes:
            break

        next_frontier: set[str] = set()
        for current in frontier:
            edges, queries = await _fetch_connected_edges(current, relationship_type=relationship_type)
            cypher_queries.extend(queries)
            for edge in edges:
                edge_key = _edge_id(edge["source"], edge["relationship_type"], edge["target"])
                edge_map[edge_key] = {
                    "id": edge_key,
                    "from": edge["source"],
                    "to": edge["target"],
                    "label": edge["relationship_type"],
                    "relationship_type": edge["relationship_type"],
                    "arrows": "to",
                }

                neighbor = edge["target"] if edge["source"] == current else edge["source"]
                if neighbor not in visited and len(visited) < max_nodes:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = sorted(next_frontier)

    metadata = await _fetch_node_records(sorted(visited))
    nodes = [
        _build_node_payload(name, metadata.get(name), is_focus=(name == node_name))
        for name in sorted(visited, key=lambda item: (item != node_name, item.lower()))
    ]

    return {
        "mode": "neighborhood",
        "focus_node": node_name,
        "depth": depth,
        "relationship_type": relationship_type,
        "nodes": nodes,
        "edges": list(edge_map.values()),
        "details": focus_details,
        "cypher_queries": cypher_queries,
    }


async def find_path_graph(
    source: str,
    target: str,
    *,
    relationship_type: str | None = None,
    max_depth: int = 4,
) -> dict[str, Any]:
    relationship_type = _validate_relationship_type(relationship_type)
    max_depth = max(1, min(max_depth, MAX_PATH_DEPTH))

    metadata = await _fetch_node_records([source, target])
    source_details = metadata.get(source)
    target_details = metadata.get(target)
    if source_details is None:
        raise ValueError(f"Node '{source}' was not found.")
    if target_details is None:
        raise ValueError(f"Node '{target}' was not found.")

    if source == target:
        return {
            "mode": "path",
            "found": True,
            "source": source,
            "target": target,
            "path": [source],
            "nodes": [_build_node_payload(source, source_details, is_focus=True, is_path=True)],
            "edges": [],
            "cypher_queries": [],
            "message": "Source and target are the same node.",
        }

    queue: deque[tuple[str, int]] = deque([(source, 0)])
    parents: dict[str, tuple[str, dict[str, str]]] = {}
    seen: set[str] = {source}
    cypher_queries: list[str] = []
    found = False

    while queue and not found:
        current, current_depth = queue.popleft()
        if current_depth >= max_depth:
            continue

        edges, queries = await _fetch_connected_edges(current, relationship_type=relationship_type)
        cypher_queries.extend(queries)
        for edge in edges:
            neighbor = edge["target"] if edge["source"] == current else edge["source"]
            if neighbor in seen:
                continue

            seen.add(neighbor)
            parents[neighbor] = (current, edge)
            if neighbor == target:
                found = True
                break
            queue.append((neighbor, current_depth + 1))

    if not found:
        return {
            "mode": "path",
            "found": False,
            "source": source,
            "target": target,
            "path": [],
            "nodes": [],
            "edges": [],
            "cypher_queries": cypher_queries,
            "message": f"No path found between {source} and {target} within {max_depth} hops.",
        }

    path_nodes = [target]
    path_edges: list[dict[str, Any]] = []
    cursor = target
    while cursor != source:
        parent, edge = parents[cursor]
        path_nodes.append(parent)
        path_edges.append({
            "id": _edge_id(edge["source"], edge["relationship_type"], edge["target"]),
            "from": edge["source"],
            "to": edge["target"],
            "label": edge["relationship_type"],
            "relationship_type": edge["relationship_type"],
            "arrows": "to",
        })
        cursor = parent
    path_nodes.reverse()
    path_edges.reverse()

    metadata = await _fetch_node_records(path_nodes)
    nodes = [
        _build_node_payload(
            name,
            metadata.get(name),
            is_focus=(name == source or name == target),
            is_path=True,
        )
        for name in path_nodes
    ]

    return {
        "mode": "path",
        "found": True,
        "source": source,
        "target": target,
        "path": path_nodes,
        "nodes": nodes,
        "edges": path_edges,
        "cypher_queries": cypher_queries,
        "message": f"Found a path with {max(0, len(path_nodes) - 1)} hop(s).",
    }


async def get_examples() -> dict[str, Any]:
    return {
        "sample_nodes": await sample_nodes(),
        "relationship_types": await list_relationship_types(),
    }
