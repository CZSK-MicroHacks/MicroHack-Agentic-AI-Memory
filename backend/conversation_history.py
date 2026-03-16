# conversation_history.py
"""
Conversation History Store — persists full conversations in Azure Cosmos DB.

TODO: Implement this class as part of Challenge 02.
      See challenges/02-conversation-history/PRD.md for the full specification.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ag_ui.conversation_history")


class ConversationHistoryStore:
    """Async CRUD wrapper around a Cosmos DB container for conversation history.

    TODO: Implement all methods. Refer to the PRD for the full API contract.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        key: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
    ):
        # TODO: Initialize the Cosmos DB client and read config from env vars
        self._container = None

    async def initialize(self) -> None:
        """Connect to existing database and container (pre-provisioned by Terraform)."""
        # TODO: Implement — get database and container clients
        pass

    async def close(self) -> None:
        """Close the underlying Cosmos client."""
        # TODO: Implement
        pass

    async def save_conversation(
        self,
        session_id: str,
        user_id: str,
        messages: list[dict[str, Any]],
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Upsert a full conversation document."""
        # TODO: Implement — build document and upsert to Cosmos DB
        return {}

    async def get_conversation(self, session_id: str, user_id: str) -> dict[str, Any] | None:
        """Read a single conversation document."""
        # TODO: Implement — point-read by session_id with user_id as partition key
        return None

    async def list_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List conversations for a user, newest first."""
        # TODO: Implement — query Cosmos DB with parameterized SQL
        return []

    async def delete_conversation(self, session_id: str, user_id: str) -> bool:
        """Hard-delete a conversation document."""
        # TODO: Implement
        return False

    async def update_title(self, session_id: str, user_id: str, title: str) -> dict[str, Any] | None:
        """Patch just the title and updated_at timestamp."""
        # TODO: Implement
        return None
