# Solution 02 — Conversation History

This solution implements conversation history persistence to Azure Cosmos DB in two parts.

## Part 1: `ConversationHistoryStore` class

Replace the contents of `backend/conversation_history.py` with:

```python
# conversation_history.py
"""
Conversation History Store — persists full conversations in Azure Cosmos DB.

Each conversation document is keyed by session_id (== thread_id) and
partitioned by user_id for efficient per-user queries.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.aio import CosmosClient, ContainerProxy
from azure.identity import DefaultAzureCredential

logger = logging.getLogger("ag_ui.conversation_history")


class ConversationHistoryStore:
    """Async CRUD wrapper around a Cosmos DB container for conversation history."""

    def __init__(
        self,
        endpoint: str | None = None,
        key: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
    ):
        self._endpoint = endpoint or os.getenv("COSMOS_ENDPOINT", "http://localhost:8081/")
        self._key = key or os.getenv("COSMOS_KEY", "")
        self._database_name = database_name or os.getenv("COSMOS_DATABASE_NAME", "conversationhistory")
        self._container_name = container_name or os.getenv("COSMOS_CONTAINER_NAME", "conversationhistory")

        # Disable SSL verification for local emulator if configured
        disable_ssl = os.getenv("COSMOS_EMULATOR_DISABLE_SSL_VERIFY", "0")
        connection_verify = disable_ssl not in ("1", "true", "yes")

        # Use AAD auth when no key is provided; fall back to key-based auth
        credential: Any
        if self._key:
            credential = self._key
            logger.info("ConversationHistoryStore: using KEY-based auth")
        else:
            credential = DefaultAzureCredential()
            logger.info("ConversationHistoryStore: using AAD auth (DefaultAzureCredential)")

        self._client = CosmosClient(
            url=self._endpoint,
            credential=credential,
            connection_verify=connection_verify,
            logging_enable=False,
        )
        self._container: ContainerProxy | None = None

    # ── Lifecycle ────────────────────────────────────────────

    async def initialize(self) -> None:
        """Connect to existing database and container (pre-provisioned by Terraform)."""
        database = self._client.get_database_client(self._database_name)
        self._container = database.get_container_client(self._container_name)
        logger.info(
            "Cosmos DB initialized: database=%s container=%s",
            self._database_name,
            self._container_name,
        )

    async def close(self) -> None:
        """Close the underlying Cosmos client."""
        await self._client.close()

    @property
    def container(self) -> ContainerProxy:
        if self._container is None:
            raise RuntimeError("ConversationHistoryStore not initialized — call await store.initialize() first")
        return self._container

    # ── CRUD ─────────────────────────────────────────────────

    async def save_conversation(
        self,
        session_id: str,
        user_id: str,
        messages: list[dict[str, Any]],
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Upsert a full conversation document."""
        now = datetime.now(timezone.utc).isoformat()

        # Try to read existing doc to preserve created_at
        created_at = now
        try:
            existing = await self.container.read_item(item=session_id, partition_key=user_id)
            created_at = existing.get("created_at", now)
        except Exception:
            pass  # new document

        doc = {
            "id": session_id,
            "user_id": user_id,
            "title": title,
            "created_at": created_at,
            "updated_at": now,
            "message_count": len(messages),
            "messages": messages,
            "metadata": metadata or {},
        }
        result = await self.container.upsert_item(doc)
        logger.info("Saved conversation id=%s user=%s messages=%d", session_id, user_id, len(messages))
        return result

    async def get_conversation(self, session_id: str, user_id: str) -> dict[str, Any] | None:
        """Read a single conversation document."""
        try:
            doc = await self.container.read_item(item=session_id, partition_key=user_id)
            return doc
        except Exception:
            return None

    async def list_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List conversations for a user, newest first."""
        query = (
            "SELECT c.id, c.user_id, c.title, c.created_at, c.updated_at, c.message_count "
            "FROM c WHERE c.user_id = @user_id "
            "ORDER BY c.updated_at DESC "
            "OFFSET @offset LIMIT @limit"
        )
        parameters = [
            {"name": "@user_id", "value": user_id},
            {"name": "@offset", "value": offset},
            {"name": "@limit", "value": limit},
        ]
        items: list[dict[str, Any]] = []
        async for item in self.container.query_items(query=query, parameters=parameters):
            items.append(item)
        return items

    async def delete_conversation(self, session_id: str, user_id: str) -> bool:
        """Hard-delete a conversation document."""
        try:
            await self.container.delete_item(item=session_id, partition_key=user_id)
            logger.info("Deleted conversation id=%s user=%s", session_id, user_id)
            return True
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status == 404:
                return False
            logger.error("Failed to delete conversation id=%s: %s", session_id, str(e), exc_info=True)
            return False

    async def update_title(self, session_id: str, user_id: str, title: str) -> dict[str, Any] | None:
        """Patch just the title and updated_at timestamp."""
        try:
            doc = await self.container.read_item(item=session_id, partition_key=user_id)
            doc["title"] = title
            doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            result = await self.container.upsert_item(doc)
            return result
        except Exception:
            return None
```

## Part 2: `_persist_turn()` function

In `backend/server.py`, replace the `_persist_turn()` body with:

```python
async def _persist_turn(
    session_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
    title: str | None,
    rag_mode: str | None = None,
) -> None:
    """Append the latest user+assistant turn to the Cosmos DB conversation."""
    try:
        new_messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ]
        metadata: dict[str, Any] = {
            "agent_name": "CustomerSupportAgent",
            "model_deployment": model_deployment,
            "api": "responses",
            "store": False,
        }
        if rag_mode:
            metadata["rag_mode"] = rag_mode

        # Fetch existing conversation to append
        existing = await conversation_store.get_conversation(session_id, user_id)
        if existing and existing.get("messages"):
            all_messages = existing["messages"] + new_messages
            # Merge metadata — keep existing keys, overwrite with new
            old_meta = existing.get("metadata") or {}
            old_meta.update(metadata)
            metadata = old_meta
        else:
            all_messages = new_messages

        await conversation_store.save_conversation(
            session_id=session_id,
            user_id=user_id,
            messages=all_messages,
            title=title,
            metadata=metadata,
        )
    except Exception as e:
        logger.error("Failed to persist turn id=%s: %s", session_id, str(e), exc_info=True)
```

## Key Concepts

- **Upsert pattern:** `save_conversation` uses Cosmos DB's `upsert_item` — it creates a new document on the first turn and replaces it on subsequent turns.
- **Append-then-upsert:** `_persist_turn` reads the existing conversation, appends the new turn, and upserts the whole document. This keeps all messages in one document.
- **Partition key:** `user_id` ensures all of a user's conversations are co-located for efficient queries.
- **Error isolation:** `_persist_turn` wraps everything in try/except so a Cosmos DB failure doesn't break the chat stream.
