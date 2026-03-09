# profile_agent.py
"""
Profile Agent — extracts personal facts from a conversation and merges them
into an existing user profile.

Uses Microsoft Agent Framework Agent with Azure OpenAI to analyse
conversation transcripts and return a structured JSON profile update.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Agent, AgentSession
from agent_framework.azure import AzureOpenAIChatClient

logger = logging.getLogger("ag_ui.profile_agent")

PROFILE_EXTRACTION_PROMPT = """\
You are a User Profile Memory agent. Your job is to analyze a conversation
and extract or update personal information about the user.

You receive:
1. The user's EXISTING profile (JSON) — may be empty for first-time creation.
2. A CONVERSATION TRANSCRIPT between the user and an assistant.

Your task:
- Identify any personal facts about the USER (not the assistant) mentioned
  in the conversation: name, location, job, interests, habits, preferences,
  current status, or any other notable personal information.
- Merge newly discovered facts into the existing profile:
  - ADD new facts that were not in the profile before.
  - UPDATE facts that have changed (e.g., user moved to a new city).
  - REMOVE facts that the user explicitly contradicts or says are no longer true.
  - LEAVE UNCHANGED any existing facts not mentioned in this conversation.
- For the `status` section, update transient state (current issues, mood, etc.)
  based on the most recent information.

Output format — respond with ONLY a JSON object (no markdown fences, no commentary):
{
  "profile_changed": true or false,
  "change_summary": "Brief description of what changed, or 'No new personal information found'",
  "facts_added": 0,
  "facts_updated": 0,
  "facts_removed": 0,
  "profile": {
    "basic_info": { ... },
    "interests": [ ... ],
    "habits": [ ... ],
    "preferences": { ... },
    "status": { ... },
    "facts": [ ... ]
  }
}

Rules:
- Output ONLY valid JSON, no markdown, no commentary.
- If the conversation contains NO personal information about the user,
  set "profile_changed" to false and return the existing profile unchanged.
- Be conservative — only extract facts clearly stated by or about the user.
- Do NOT infer or guess information not explicitly mentioned.
- Do NOT include information about the assistant or the system.
- Keep string values concise (under 100 characters each).
- Keep arrays to a reasonable size (max ~20 items per category).
- Deduplicate — do not add facts that are already captured.
"""


@dataclass
class ProfileExtractionResult:
    """Output of the profile extraction agent."""
    changed: bool
    summary: str
    facts_added: int = 0
    facts_updated: int = 0
    facts_removed: int = 0
    profile: dict[str, Any] = field(default_factory=dict)


class ProfileAgent:
    """Extracts user profile facts from conversations."""

    def __init__(self, chat_client: AzureOpenAIChatClient):
        self._agent = Agent(
            name="ProfileExtractor",
            instructions=PROFILE_EXTRACTION_PROMPT,
            client=chat_client,
        )

    async def extract_profile(
        self,
        existing_profile: dict[str, Any] | None,
        conversation_messages: list[dict[str, Any]],
        conversation_id: str,
    ) -> ProfileExtractionResult:
        """
        Analyze a conversation and return an updated user profile.

        Args:
            existing_profile: Current profile sections or None for first-time.
            conversation_messages: The conversation message list.
            conversation_id: ID of the source conversation (for logging).

        Returns:
            ProfileExtractionResult with the merged profile.
        """
        # Build the prompt input
        existing_sections = {
            "basic_info": {},
            "interests": [],
            "habits": [],
            "preferences": {},
            "status": {},
            "facts": [],
        }
        if existing_profile:
            for key in existing_sections:
                if key in existing_profile:
                    existing_sections[key] = existing_profile[key]

        prompt_input = self._build_prompt(existing_sections, conversation_messages)

        # Run the agent
        raw_response = await self._run_agent(prompt_input)

        logger.info(
            "Profile extraction RAW RESPONSE for conversation=%s:\n%s",
            conversation_id,
            raw_response,
        )
        print(f"Profile extraction RAW RESPONSE for conversation={conversation_id}:\n{raw_response}")
        # Parse the JSON response
        result = self._parse_response(raw_response, existing_sections)

        return result

    def _build_prompt(
        self,
        existing_sections: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> str:
        """Build the agent input: existing profile + conversation transcript."""
        parts: list[str] = []

        parts.append("EXISTING PROFILE:")
        parts.append(json.dumps(existing_sections, indent=2))

        parts.append("")
        parts.append("CONVERSATION:")

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                parts.append(f"{role}: {content}")
            for tc in msg.get("tool_calls", []):
                name = tc.get("name", "unknown_tool")
                args = tc.get("arguments", "")
                parts.append(f"[tool call: {name}({args})]")
            for tr in msg.get("tool_results", []):
                result = tr.get("result", "")
                parts.append(f"[tool result: {result}]")

        return "\n".join(parts)

    async def _run_agent(self, prompt_input: str) -> str:
        """Run the Agent and collect the full response."""
        session = AgentSession()

        full_text: list[str] = []
        async for update in self._agent.run(prompt_input, stream=True, session=session):
            if update.text:
                full_text.append(update.text)

        response = "".join(full_text).strip()
        if not response:
            response = '{"profile_changed": false, "change_summary": "No response from agent", "facts_added": 0, "facts_updated": 0, "facts_removed": 0, "profile": {}}'
        return response

    def _parse_response(
        self,
        raw: str,
        fallback_sections: dict[str, Any],
    ) -> ProfileExtractionResult:
        """Parse the agent's JSON response into a ProfileExtractionResult."""
        # Strip markdown code fences if present
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse profile agent response: %s — raw: %s", e, raw[:500])
            return ProfileExtractionResult(
                changed=False,
                summary="Failed to parse agent response",
                profile=fallback_sections,
            )

        changed = data.get("profile_changed", False)
        summary = data.get("change_summary", "No summary")
        facts_added = data.get("facts_added", 0)
        facts_updated = data.get("facts_updated", 0)
        facts_removed = data.get("facts_removed", 0)
        profile = data.get("profile", fallback_sections)

        # Ensure all expected sections exist
        for key in fallback_sections:
            if key not in profile:
                profile[key] = fallback_sections[key]

        return ProfileExtractionResult(
            changed=changed,
            summary=summary,
            facts_added=facts_added,
            facts_updated=facts_updated,
            facts_removed=facts_removed,
            profile=profile,
        )
