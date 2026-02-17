# agent_tools.py
"""
Agent tools for the Customer Support Agent.

Encapsulates all @tool-decorated functions used by the ChatAgent,
with dependencies injected via the AgentTools class constructor.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Annotated, Any

from pydantic import Field

from agent_framework import tool

from classic_rag_client import ClassicRAGClient
from conversation_memory import ConversationMemoryStore
from memory_agent import MemoryAgent
from rag_client import RAGClient
from user_profile_memory import UserProfileMemoryStore

logger = logging.getLogger("ag_ui.agent_tools")


def _json_merge_patch(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """RFC 7396 JSON Merge Patch — recursive merge with null-removal."""
    result = dict(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _json_merge_patch(result[key], value)
        else:
            result[key] = value
    return result


# Status → Material Symbol icon name mapping
_STATUS_ICONS = {
    "shipped": "local_shipping",
    "processing": "pending",
    "delivered": "check_circle",
    "not_found": "error",
}


class AgentTools:
    """All agent-callable tools with injected store/client dependencies.

    Usage::

        tools = AgentTools(memory_store, memory_agent, profile_store, rag_client)
        # Pass bound methods as tools:
        agent = ChatAgent(..., tools=tools.all)
        # Before each agent run:
        tools.set_user_id(user_id)
    """

    def __init__(
        self,
        memory_store: ConversationMemoryStore,
        memory_agent: MemoryAgent,
        profile_store: UserProfileMemoryStore,
        rag_client: RAGClient,
        classic_rag_client: ClassicRAGClient,
    ) -> None:
        self._memory_store = memory_store
        self._memory_agent = memory_agent
        self._profile_store = profile_store
        self._rag_client = rag_client
        self._classic_rag_client = classic_rag_client
        self._current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
            "_current_user_id"
        )

    def set_user_id(self, user_id: str) -> None:
        """Set the active user_id for the current async context."""
        self._current_user_id.set(user_id)

    # -----------------------------------------------------------------
    # Tool definitions
    # -----------------------------------------------------------------

    @tool
    async def check_memory(
        self,
        query: Annotated[str, Field(description="Natural-language query to search past conversations")],
    ) -> str:
        """Search the user's conversation memory for relevant past conversations.

        Use this tool when the user explicitly references or asks about something
        from a previous conversation. Returns the top 3 most relevant conversation
        summaries based on semantic similarity.
        """
        user_id = self._current_user_id.get()
        logger.info("Running check_memory tool with query: %s for user: %s", query, user_id)
        query_embedding = await self._memory_agent._embed(query)

        rows = await self._memory_store.search(
            user_id=user_id,
            query_embedding=query_embedding,
            limit=3,
        )

        if not rows:
            logger.info("No relevant past conversations found for query: %s", query)
            return "No relevant past conversations found."

        logger.info("Found %d relevant conversations for query: %s", len(rows), query)
        results = []
        for i, row in enumerate(rows, 1):
            results.append(f"{i}. {row['summary']}")

        return "\n".join(results)

    @tool
    def get_order_status(
        self,
        order_id: Annotated[str, Field(description="The order ID to look up (e.g., ORD-001)")],
    ) -> dict:
        """Look up the status of a customer order.

        Returns a data model ready for the Shipping Status A2UI template:
          trackingNumber  – display string with tracking code
          currentStepIcon – Material Symbol name for the active step
          eta             – estimated delivery display string
        """
        orders = {
            "ORD-001": {"status": "shipped",    "tracking": "1Z999AA1", "eta": "Jan 25, 2026"},
            "ORD-002": {"status": "processing", "tracking": None,       "eta": "Jan 23, 2026"},
            "ORD-003": {"status": "delivered",  "tracking": "1Z999AA3", "eta": "Delivered Jan 20"},
        }
        raw = orders.get(order_id)

        if raw is None:
            return {
                "trackingNumber": "Tracking: N/A",
                "currentStepIcon": "error",
                "eta": "Order not found",
            }

        return {
            "trackingNumber": f"Tracking: {raw['tracking']}" if raw.get("tracking") else "Tracking: N/A",
            "currentStepIcon": _STATUS_ICONS.get(raw["status"], "help"),
            "eta": f"Estimated delivery: {raw['eta']}" if raw.get("eta") else "",
        }

    @tool
    async def do_rag(
        self,
        query: Annotated[str, Field(description="Natural-language question to search the knowledge base for")],
    ) -> dict:
        """Search the company knowledge base for detailed information about orders,
        products, shipping, and return/refund policies.

        Use this tool when you need:
        - Detailed product specifications or descriptions
        - Shipping carrier, weight, or packaging information
        - Return policy rules, eligibility windows, or refund timelines
        - Any information beyond the basic order status

        Do NOT use this tool for a simple order status check — use
        get_order_status for that instead.
        """
        logger.info("Running do_rag tool with query: %s", query)
        try:
            result = await self._rag_client.retrieve(query=query)
        except Exception as e:
            logger.error("do_rag tool failed: %s", e, exc_info=True)
            return {"content": f"Knowledge base search failed: {e}", "citations": []}

        if not result.content and not result.citations:
            return {"content": "No relevant information found in the knowledge base.", "citations": []}

        citations_list = []
        for i, cit in enumerate(result.citations):
            citations_list.append({
                "search_idx": i,
                "ref_id": cit.ref_id,
                "source_name": cit.source_name,
                "content": cit.content,
                "annotation": f"\u3010{i}:{cit.ref_id}\u2020{cit.source_name}\u3011",
            })

        return {
            "content": result.content,
            "citations": citations_list,
        }

    @tool
    async def do_classic_rag(
        self,
        query: Annotated[str, Field(description="Natural-language question to search the orders index for")],
    ) -> dict:
        """Search the orders knowledge base using classic hybrid search (text + vector + semantic ranking).

        This tool searches ONLY the orders index. Use it for:
        - Product details within specific orders
        - Shipping carrier, weight, or packaging information for orders
        - Order-specific information beyond the basic status

        This tool does NOT cover return/refund policies — those require
        the agentic RAG tool which spans multiple knowledge sources.
        """
        logger.info("Running do_classic_rag tool with query: %s", query)
        try:
            result = await self._classic_rag_client.search(query=query)
        except Exception as e:
            logger.error("do_classic_rag tool failed: %s", e, exc_info=True)
            return {"content": f"Knowledge base search failed: {e}", "citations": []}

        if not result.content and not result.citations:
            return {"content": "No relevant information found in the knowledge base.", "citations": []}

        citations_list = []
        for i, cit in enumerate(result.citations):
            citations_list.append({
                "search_idx": i,
                "ref_id": cit.ref_id,
                "source_name": cit.source_name,
                "content": cit.content,
                "annotation": f"\u3010{i}:{cit.ref_id}\u2020{cit.source_name}\u3011",
            })

        return {
            "content": result.content,
            "citations": citations_list,
        }

    @tool
    async def update_user_profile(
        self,
        basic_info: Annotated[dict[str, Any] | None, Field(
            default=None,
            description="Object with keys like name, location, job, company. Only include changed fields.",
        )] = None,
        interests: Annotated[list[str] | None, Field(
            default=None,
            description="Full list of user interests (merge new items with existing ones).",
        )] = None,
        habits: Annotated[list[str] | None, Field(
            default=None,
            description="Full list of user habits (merge new items with existing ones).",
        )] = None,
        preferences: Annotated[dict[str, Any] | None, Field(
            default=None,
            description="Object with user preferences. Only include changed fields.",
        )] = None,
        status: Annotated[dict[str, Any] | None, Field(
            default=None,
            description="Object with current life status or events. Only include changed fields.",
        )] = None,
        facts: Annotated[list[str] | None, Field(
            default=None,
            description="Full list of personal facts (pets, allergies, family, birthday, etc.).",
        )] = None,
    ) -> str:
        """Update the user's stored profile with new personal information.

        Call this when the user explicitly mentions new or changed personal
        information. Pass only the fields that changed.
        """
        user_id = self._current_user_id.get()

        # Build patch from non-None arguments
        patch_dict: dict[str, Any] = {}
        if basic_info is not None:
            patch_dict["basic_info"] = basic_info
        if interests is not None:
            patch_dict["interests"] = interests
        if habits is not None:
            patch_dict["habits"] = habits
        if preferences is not None:
            patch_dict["preferences"] = preferences
        if status is not None:
            patch_dict["status"] = status
        if facts is not None:
            patch_dict["facts"] = facts

        logger.info("Running update_user_profile tool for user: %s with patch: %s", user_id, patch_dict)

        if not patch_dict:
            return "No profile fields provided"

        # Read current profile
        existing = await self._profile_store.get_profile(user_id)
        existing_sections: dict[str, Any] = {
            "basic_info": {},
            "interests": [],
            "habits": [],
            "preferences": {},
            "status": {},
            "facts": [],
        }
        if existing:
            for key in existing_sections:
                if key in existing:
                    existing_sections[key] = existing[key]

        # Apply merge patch
        merged = _json_merge_patch(existing_sections, patch_dict)

        # Upsert to Cosmos DB
        await self._profile_store.upsert_profile(
            user_id=user_id,
            profile_sections=merged,
            source_conversation=None,
        )

        # Return summary
        changed_keys = list(patch_dict.keys())
        summary = f"Profile updated: {', '.join(changed_keys)}"
        logger.info("Profile updated for user=%s: %s", user_id, summary)
        return summary

    # -----------------------------------------------------------------
    # Tool list accessors
    # -----------------------------------------------------------------

    @property
    def all(self) -> list:
        """All tools including agentic RAG."""
        return [self.get_order_status, self.check_memory, self.do_rag, self.update_user_profile]

    def for_rag_mode(self, rag_mode: str) -> list:
        """Return tool list for the given RAG mode."""
        base = [self.get_order_status, self.check_memory, self.update_user_profile]
        if rag_mode == "agentic":
            return base + [self.do_rag]
        elif rag_mode == "classic":
            return base + [self.do_classic_rag]
        return base  # "none"
