# conversation_memory.py
"""
Conversation Memory Store — persists summarised conversation items with vector
embeddings in PostgreSQL (pgvector).

Each row corresponds to exactly one Conversation History document in Cosmos DB,
identified by (conversation_id, user_id).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import asyncpg

logger = logging.getLogger("ag_ui.conversation_memory")


class ConversationMemoryStore:
    """Async CRUD + vector-similarity search over PostgreSQL + pgvector."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ):
        self._host = host or os.getenv("PG_HOST", "localhost")
        self._port = port or int(os.getenv("PG_PORT", "5432"))
        self._user = user or os.getenv("PG_USER", "app")
        self._password = password or os.getenv("PG_PASSWORD", "app_pwd")
        self._database = database or os.getenv("PG_DATABASE", "appdb")
        self._pool: asyncpg.Pool | None = None

    # ── Lifecycle ────────────────────────────────────────────

    async def initialize(self) -> None:
        """Create connection pool and ensure the table + extension exist."""
        self._pool = await asyncpg.create_pool(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
            min_size=2,
            max_size=10,
        )

        # Register the vector type codec so asyncpg can handle vector columns
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_memory (
                    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    conversation_id TEXT         NOT NULL,
                    user_id         TEXT         NOT NULL,
                    summary         TEXT         NOT NULL,
                    embedding       vector(3072) NOT NULL,
                    source_title    TEXT,
                    message_count   INT          NOT NULL DEFAULT 0,
                    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
                    CONSTRAINT uq_conversation_memory UNIQUE (conversation_id, user_id)
                )
            """)

        logger.info(
            "PostgreSQL memory store initialized: %s@%s:%s/%s",
            self._user, self._host, self._port, self._database,
        )

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL memory store closed")

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError(
                "ConversationMemoryStore not initialized — call await store.initialize() first"
            )
        return self._pool

    # ── CRUD ─────────────────────────────────────────────────

    async def create_memory(
        self,
        conversation_id: str,
        user_id: str,
        summary: str,
        embedding: list[float],
        source_title: str | None = None,
        message_count: int = 0,
    ) -> dict[str, Any]:
        """
        Insert or update a conversation memory row.

        Uses ON CONFLICT … DO UPDATE so re-memorising an already-memorised
        conversation simply replaces the summary and embedding.
        """
        # Format embedding as pgvector literal
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        row = await self.pool.fetchrow(
            """
            INSERT INTO conversation_memory
                (conversation_id, user_id, summary, embedding, source_title, message_count)
            VALUES
                ($1, $2, $3, $4::vector, $5, $6)
            ON CONFLICT (conversation_id, user_id) DO UPDATE SET
                summary       = EXCLUDED.summary,
                embedding     = EXCLUDED.embedding,
                source_title  = EXCLUDED.source_title,
                message_count = EXCLUDED.message_count,
                updated_at    = now()
            RETURNING id, conversation_id, user_id, summary, source_title,
                      message_count, created_at, updated_at
            """,
            conversation_id, user_id, summary, embedding_str,
            source_title, message_count,
        )
        logger.info(
            "Upserted memory conversation_id=%s user=%s",
            conversation_id, user_id,
        )
        return dict(row) if row else {}

    async def get_memory(
        self, conversation_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Read a single memory by conversation_id + user_id."""
        row = await self.pool.fetchrow(
            """
            SELECT id, conversation_id, user_id, summary, source_title,
                   message_count, created_at, updated_at
            FROM conversation_memory
            WHERE conversation_id = $1 AND user_id = $2
            """,
            conversation_id, user_id,
        )
        return dict(row) if row else None

    async def list_memories(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List memories for a user, newest first (excludes embedding)."""
        rows = await self.pool.fetch(
            """
            SELECT id, conversation_id, user_id, summary, source_title,
                   message_count, created_at, updated_at
            FROM conversation_memory
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id, limit, offset,
        )
        return [dict(r) for r in rows]

    async def delete_memory(
        self, conversation_id: str, user_id: str
    ) -> bool:
        """Delete a memory row. Returns True if a row was removed."""
        result = await self.pool.execute(
            """
            DELETE FROM conversation_memory
            WHERE conversation_id = $1 AND user_id = $2
            """,
            conversation_id, user_id,
        )
        deleted = result == "DELETE 1"
        if deleted:
            logger.info(
                "Deleted memory conversation_id=%s user=%s",
                conversation_id, user_id,
            )
        return deleted

    async def search(
        self,
        user_id: str,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Cosine-similarity search scoped to a single user.

        Returns the top-N most similar memories with a similarity score
        in [0, 1] (1 = identical).
        """
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        rows = await self.pool.fetch(
            """
            SELECT id, conversation_id, user_id, summary, source_title,
                   message_count, created_at, updated_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM conversation_memory
            WHERE user_id = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            embedding_str, user_id, limit,
        )
        return [dict(r) for r in rows]
