# conversation_history.py
"""
Conversation History Store — persists full conversations in Azure Cosmos DB.

Distinction from SessionManager:
  - SessionManager handles *live* session state (AgentSession)
    for the currently active conversation turn. Ephemeral / in-memory.
  - ConversationHistoryStore is the *durable* record of every conversation,
    stored as a JSON document in Cosmos DB with full metadata.

Each conversation document is keyed by session_id (== thread_id) and
partitioned by user_id for efficient per-user queries.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import PartitionKey
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

        # Use AAD auth (DefaultAzureCredential / managed identity) when no key
        # is provided; fall back to key-based auth for local emulator.
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
        """
        Upsert a full conversation document.

        Called after every completed agent run so the durable record stays
        in sync with the live session.
        """
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
        """
        List conversations for a user, newest first.

        Returns lightweight summaries (no messages body) for the list view.
        """
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
                logger.debug("Conversation not found for deletion id=%s user=%s", session_id, user_id)
                return False

            # The Cosmos DB vnext-preview emulator returns a malformed HTTP
            # response for DELETE operations (body is `null` instead of valid
            # HTTP).  The delete itself succeeds — verify with a point-read.
            err_msg = str(e)
            if "Expected HTTP/" in err_msg or "ServiceResponseError" in type(e).__name__:
                try:
                    await self.container.read_item(item=session_id, partition_key=user_id)
                    # Still exists → delete really failed
                    logger.error("Delete failed (item still exists) id=%s: %s", session_id, err_msg)
                    return False
                except Exception:
                    # Item is gone — delete succeeded despite the bad response
                    logger.info("Deleted conversation id=%s user=%s (emulator workaround)", session_id, user_id)
                    return True

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
