"""
Load entity and concept nodes into the PostgreSQL nodes table with embeddings.

Reads: data/entities.json, data/concepts.json
Inserts into: public.nodes (with computed embeddings and auto-generated tsvector)
"""

import asyncio
import logging

import asyncpg

from helpers import get_openai_client, compute_embeddings, load_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kg.load_nodes")


async def main():
    import os
    from dotenv import load_dotenv
    load_dotenv()

    client = get_openai_client()

    # Load entities + concepts
    entities = load_json("entities.json")
    concepts = load_json("concepts.json")

    # Build node records: entities + concept nodes
    nodes = []
    for e in entities:
        nodes.append({
            "node_type": e["node_type"],
            "name": e["name"],
            "description": e["description"],
            "properties": e.get("properties", {}),
        })
    for c in concepts:
        nodes.append({
            "node_type": "concept",
            "name": c["name"],
            "description": c["description"],
            "properties": c.get("properties", {}),
        })

    logger.info("Computing embeddings for %d nodes...", len(nodes))
    texts = [f"{n['name']}: {n['description']}" for n in nodes]
    embeddings = compute_embeddings(client, texts)

    # Connect to PG and insert
    pool = await asyncpg.create_pool(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5433")),
        user=os.getenv("PG_USER", "app"),
        password=os.getenv("PG_PASSWORD", "app_pwd"),
        database=os.getenv("PG_DATABASE", "appdb"),
    )

    import json
    async with pool.acquire() as conn:
        # Clear existing nodes
        await conn.execute("DELETE FROM nodes")
        logger.info("Cleared existing nodes")

        inserted = 0
        for node, emb in zip(nodes, embeddings):
            embedding_str = "[" + ",".join(str(v) for v in emb) + "]"
            props_json = json.dumps(node["properties"])
            try:
                await conn.execute(
                    """
                    INSERT INTO nodes (node_type, name, description, properties, embedding)
                    VALUES ($1, $2, $3, $4::jsonb, $5::vector)
                    ON CONFLICT (node_type, name) DO UPDATE SET
                        description = EXCLUDED.description,
                        properties = EXCLUDED.properties,
                        embedding = EXCLUDED.embedding
                    """,
                    node["node_type"], node["name"], node["description"],
                    props_json, embedding_str,
                )
                inserted += 1
            except Exception as e:
                logger.error("Failed to insert %s/%s: %s", node["node_type"], node["name"], e)

        logger.info("Inserted %d nodes", inserted)

        # Verify counts
        rows = await conn.fetch(
            "SELECT node_type, count(*) as cnt FROM nodes GROUP BY node_type ORDER BY node_type"
        )
        for r in rows:
            logger.info("  %s: %d", r["node_type"], r["cnt"])

    await pool.close()
    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
