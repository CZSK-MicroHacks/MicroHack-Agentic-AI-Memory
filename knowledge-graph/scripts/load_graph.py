"""
Load relationships into the Apache AGE graph.

1. Creates graph vertices for every node in the nodes table
2. Creates typed edges from data/relationships.json
3. Creates belongs_to_community edges from data/concepts.json

Reads: data/relationships.json, data/concepts.json
Uses: PostgreSQL AGE extension (Cypher via SQL)
"""

import asyncio
import json
import logging
import os

import asyncpg
from dotenv import load_dotenv

from helpers import load_json

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kg.load_graph")


def _escape(s: str) -> str:
    """Escape single quotes for Cypher string literals."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


async def _cypher(conn: asyncpg.Connection, query: str, return_cols: str = "v agtype") -> list:
    """Execute a Cypher query through AGE's SQL wrapper."""
    sql = f"""SELECT * FROM cypher('biomedical', $$ {query} $$) AS ({return_cols});"""
    try:
        return await conn.fetch(sql)
    except Exception as e:
        logger.error("Cypher failed: %s\nQuery: %s", e, query[:200])
        raise


async def main():
    import ssl
    ssl_ctx = ssl.create_default_context()
    pool = await asyncpg.create_pool(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        user=os.getenv("PG_USER", "pgadmin"),
        password=os.getenv("PG_PASSWORD", ""),
        database=os.getenv("PG_DATABASE", "appdb"),
        ssl=ssl_ctx,
    )

    async with pool.acquire() as conn:
        # Enable AGE search path in this session
        await conn.execute("SET search_path = ag_catalog, \"$user\", public;")

        # --- Step 1: Create vertices for all nodes ---
        logger.info("Creating graph vertices...")
        nodes = await conn.fetch("SELECT id, node_type, name FROM nodes ORDER BY node_type, name")

        # Build name→UUID lookup
        name_to_uuid = {}
        for row in nodes:
            name_to_uuid[row["name"]] = str(row["id"])

        # Clear existing graph data (drop and recreate labels would be complex, so just delete vertices/edges)
        try:
            await _cypher(conn, "MATCH (n) DETACH DELETE n", "v agtype")
        except Exception:
            pass  # Graph might be empty

        vertex_count = 0
        for row in nodes:
            name = _escape(row["name"])
            node_type = row["node_type"]
            uuid = str(row["id"])
            label = node_type.capitalize()  # Drug, Disease, Gene, Symptom, Pathway, Concept

            cypher = f"CREATE (:{label} {{name: '{name}', node_id: '{uuid}'}})"
            try:
                await _cypher(conn, cypher, "v agtype")
                vertex_count += 1
            except Exception as e:
                logger.warning("Failed to create vertex %s/%s: %s", node_type, row["name"], e)

        logger.info("Created %d vertices", vertex_count)

        # --- Step 2: Create relationship edges ---
        logger.info("Creating relationship edges...")
        relationships = load_json("relationships.json")
        edge_count = 0

        for rel in relationships:
            source = _escape(rel["source"])
            target = _escape(rel["target"])
            rel_type = rel["relationship_type"].upper()
            props = rel.get("properties", {})
            strength = _escape(props.get("strength", "moderate"))
            evidence = _escape(props.get("evidence", "established"))

            cypher = (
                f"MATCH (a {{name: '{source}'}}), (b {{name: '{target}'}}) "
                f"CREATE (a)-[:{rel_type} {{strength: '{strength}', evidence: '{evidence}'}}]->(b)"
            )
            try:
                await _cypher(conn, cypher, "v agtype")
                edge_count += 1
            except Exception as e:
                logger.warning("Failed edge %s -[%s]-> %s: %s",
                             rel["source"], rel["relationship_type"], rel["target"], e)

        logger.info("Created %d relationship edges", edge_count)

        # --- Step 3: Create belongs_to_community edges ---
        logger.info("Creating community membership edges...")
        concepts = load_json("concepts.json")
        community_count = 0

        for concept in concepts:
            concept_name = _escape(concept["name"])
            for member_name in concept["members"]:
                member = _escape(member_name)
                cypher = (
                    f"MATCH (a {{name: '{member}'}}), (c {{name: '{concept_name}'}}) "
                    f"CREATE (a)-[:BELONGS_TO_COMMUNITY]->(c)"
                )
                try:
                    await _cypher(conn, cypher, "v agtype")
                    community_count += 1
                except Exception as e:
                    logger.warning("Failed community edge %s -> %s: %s",
                                 member_name, concept["name"], e)

        logger.info("Created %d community membership edges", community_count)

        # --- Verify ---
        result = await _cypher(conn, "MATCH (n) RETURN count(n)", "cnt agtype")
        logger.info("Total vertices in graph: %s", result[0]["cnt"] if result else "?")

        result = await _cypher(conn, "MATCH ()-[r]->() RETURN count(r)", "cnt agtype")
        logger.info("Total edges in graph: %s", result[0]["cnt"] if result else "?")

    await pool.close()
    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
