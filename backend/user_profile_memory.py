# user_profile_memory.py
"""
User Profile Memory Store — persists a single evolving profile document per
user in Azure Cosmos DB.

The profile captures personal facts (interests, habits, preferences, etc.)
extracted from conversations over time.

Storage: Cosmos DB database ``userprofiles``, container ``userprofiles``,
partition key ``/user_id``.  One JSON document per user, keyed by user_id.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient, ContainerProxy
from azure.identity import DefaultAzureCredential

logger = logging.getLogger("ag_ui.user_profile_memory")

# Default empty profile skeleton
_EMPTY_PROFILE_SECTIONS: dict[str, Any] = {
    "basic_info": {},
    "interests": [],
    "habits": [],
    "preferences": {},
    "status": {},
    "facts": [],
}


class UserProfileMemoryStore:
    """Async CRUD for user profile documents stored in Cosmos DB."""

    def __init__(
        self,
        endpoint: str | None = None,
        key: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
    ):
        self._endpoint = endpoint or os.getenv("COSMOS_ENDPOINT", "http://localhost:8081/")
        self._key = key or os.getenv("COSMOS_KEY", "")
        self._database_name = database_name or os.getenv("COSMOS_UPM_DATABASE_NAME", "userprofiles")
        self._container_name = container_name or os.getenv("COSMOS_UPM_CONTAINER_NAME", "userprofiles")

        disable_ssl = os.getenv("COSMOS_EMULATOR_DISABLE_SSL_VERIFY", "0")
        connection_verify = disable_ssl not in ("1", "true", "yes")

        # Use AAD auth (DefaultAzureCredential / managed identity) when no key
        # is provided; fall back to key-based auth for local emulator.
        credential: Any
        if self._key:
            credential = self._key
            logger.info("UserProfileMemoryStore: using KEY-based auth")
        else:
            credential = DefaultAzureCredential()
            logger.info("UserProfileMemoryStore: using AAD auth (DefaultAzureCredential)")

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
            "Cosmos DB user-profile store initialized: database=%s container=%s",
            self._database_name,
            self._container_name,
        )

    async def close(self) -> None:
        """Close the underlying Cosmos client."""
        await self._client.close()

    @property
    def container(self) -> ContainerProxy:
        if self._container is None:
            raise RuntimeError(
                "UserProfileMemoryStore not initialized — call await store.initialize() first"
            )
        return self._container

    # ── CRUD ─────────────────────────────────────────────────

    async def get_profile(self, user_id: str) -> dict[str, Any] | None:
        """Point-read a user profile.  Returns ``None`` if it does not exist."""
        try:
            doc = await self.container.read_item(item=user_id, partition_key=user_id)
            return doc
        except Exception:
            return None

    async def upsert_profile(
        self,
        user_id: str,
        profile_sections: dict[str, Any],
        source_conversation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create or fully replace a user profile document.

        ``profile_sections`` must contain the top-level keys
        (basic_info, interests, habits, preferences, status, facts).

        If ``source_conversation`` is provided it is appended to the audit
        trail.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Try to read existing doc to preserve metadata
        existing = await self.get_profile(user_id)

        if existing:
            version = existing.get("version", 0) + 1
            created_at = existing.get("created_at", now)
            source_conversations = existing.get("source_conversations", [])
        else:
            version = 1
            created_at = now
            source_conversations = []

        if source_conversation:
            source_conversations.append(source_conversation)

        doc: dict[str, Any] = {
            "id": user_id,
            "user_id": user_id,
            "version": version,
            **{k: profile_sections.get(k, _EMPTY_PROFILE_SECTIONS.get(k)) for k in _EMPTY_PROFILE_SECTIONS},
            "source_conversations": source_conversations,
            "created_at": created_at,
            "updated_at": now,
        }

        result = await self.container.upsert_item(doc)
        logger.info("Upserted user profile user=%s version=%d", user_id, version)
        return result

    async def patch_profile(
        self,
        user_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Partial update — merge provided fields into the existing profile.

        Only keys present in ``updates`` are overwritten; others are kept.
        Returns ``None`` if the profile does not exist.
        """
        existing = await self.get_profile(user_id)
        if existing is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        for key in _EMPTY_PROFILE_SECTIONS:
            if key in updates and updates[key] is not None:
                existing[key] = updates[key]

        existing["version"] = existing.get("version", 0) + 1
        existing["updated_at"] = now

        result = await self.container.upsert_item(existing)
        logger.info("Patched user profile user=%s version=%d", user_id, existing["version"])
        return result

    async def delete_profile(self, user_id: str) -> bool:
        """Hard-delete a user profile document."""
        try:
            await self.container.delete_item(item=user_id, partition_key=user_id)
            logger.info("Deleted user profile user=%s", user_id)
            return True
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status == 404:
                return False

            # Cosmos DB emulator workaround (same as conversation_history.py)
            err_msg = str(e)
            if "Expected HTTP/" in err_msg or "ServiceResponseError" in type(e).__name__:
                try:
                    await self.container.read_item(item=user_id, partition_key=user_id)
                    return False
                except Exception:
                    logger.info("Deleted user profile user=%s (emulator workaround)", user_id)
                    return True

            logger.error("Failed to delete profile user=%s: %s", user_id, str(e), exc_info=True)
            return False
