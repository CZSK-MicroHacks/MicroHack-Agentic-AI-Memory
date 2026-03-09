# memory_agent.py
"""
Memory Agent — summarises a conversation and generates its vector embedding.

Uses:
  - Microsoft Agent Framework Agent for summarisation (AZURE_OPENAI_DEPLOYMENT_NAME)
  - Azure OpenAI Embeddings API for vectorisation (AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jinja2
from agent_framework import Agent, AgentSession
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

logger = logging.getLogger("ag_ui.memory_agent")

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
    undefined=jinja2.StrictUndefined,
)

SUMMARIZATION_PROMPT = _jinja_env.get_template("conversation_memory.j2").render().strip()


@dataclass
class MemoryResult:
    """Output of the memory agent: a summary string and its embedding vector."""
    summary: str
    embedding: list[float]


class MemoryAgent:
    """Summarises a conversation and generates its embedding."""

    def __init__(
        self,
        chat_client: AzureOpenAIChatClient,
        embedding_deployment: str | None = None,
        openai_endpoint: str | None = None,
    ):
        # Summariser agent
        self._summarizer = Agent(
            name="MemorySummarizer",
            instructions=SUMMARIZATION_PROMPT,
            client=chat_client,
        )

        # Embedding client (uses the Azure OpenAI Python SDK directly)
        endpoint = openai_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")
        self._embedding_deployment = embedding_deployment or os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large"
        )

        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )

        self._embedding_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version="2024-06-01",
        )

    # ── Public API ───────────────────────────────────────────

    async def create_memory(
        self,
        conversation_messages: list[dict[str, Any]],
        title: str | None = None,
    ) -> MemoryResult:
        """
        1. Format the conversation into a prompt
        2. Run the summariser agent to get a concise summary
        3. Generate an embedding from the summary
        4. Return MemoryResult(summary, embedding)
        """
        # Step 1 — build a textual representation of the conversation
        conversation_text = self._format_conversation(conversation_messages, title)

        # Step 2 — summarise via Agent
        summary = await self._summarize(conversation_text)

        # Step 3 — embed the summary
        embedding = await self._embed(summary)

        logger.info(
            "Created memory: summary_len=%d embedding_dims=%d",
            len(summary), len(embedding),
        )
        return MemoryResult(summary=summary, embedding=embedding)

    # ── Internals ────────────────────────────────────────────

    def _format_conversation(
        self,
        messages: list[dict[str, Any]],
        title: str | None = None,
    ) -> str:
        """Turn a list of message dicts into a readable transcript."""
        parts: list[str] = []
        if title:
            parts.append(f"Conversation title: {title}")
            parts.append("")

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                parts.append(f"{role}: {content}")

            # Include tool call info if present
            for tc in msg.get("tool_calls", []):
                name = tc.get("name", "unknown_tool")
                args = tc.get("arguments", "")
                parts.append(f"[tool call: {name}({args})]")
            for tr in msg.get("tool_results", []):
                result = tr.get("result", "")
                parts.append(f"[tool result: {result}]")

        return "\n".join(parts)

    async def _summarize(self, conversation_text: str) -> str:
        """Run the summariser agent and return the summary text."""
        session = AgentSession()

        full_text: list[str] = []
        async for update in self._summarizer.run(
            f"Summarise the following conversation:\n\n{conversation_text}",
            stream=True,
            session=session,
        ):
            if update.text:
                full_text.append(update.text)

        summary = "".join(full_text).strip()
        if not summary:
            summary = "No summary could be generated."
        return summary

    async def _embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text."""
        response = await self._embedding_client.embeddings.create(
            model=self._embedding_deployment,
            input=text,
        )
        return response.data[0].embedding
