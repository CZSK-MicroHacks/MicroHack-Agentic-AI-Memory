# orchestrator.py
"""
Orchestrator for the multi-agent travel planning workflow.

The Facilitator agent uses tools to create tasks and dispatch specialist agents.
Specialist dispatch is implemented as tools so the LLM decides when to call each agent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated, Any

import jinja2
from pydantic import Field

from agent_framework import Agent, AgentThread, ChatMessageStore, tool
from agent_framework.azure import AzureOpenAIChatClient

from scratchpad import TaskBoard, SharedDocument
from tools import FacilitatorTools
from agents import run_agent
from events import EventEmitter

logger = logging.getLogger("travel.orchestrator")

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
)


class AgentDispatcher:
    """Tools for the facilitator to dispatch specialist agents.

    Each dispatch tool runs a specialist agent end-to-end and returns
    a brief summary of what was accomplished.
    """

    def __init__(
        self,
        chat_client: AzureOpenAIChatClient,
        task_board: TaskBoard,
        document: SharedDocument,
        emitter: EventEmitter,
    ) -> None:
        self._chat_client = chat_client
        self._task_board = task_board
        self._document = document
        self._emitter = emitter

    @tool
    async def call_logistics_agent(
        self,
        task_ids: Annotated[list[int], Field(description="Task IDs for the logistics agent to work on")],
        message: Annotated[str, Field(description="Brief instruction for the logistics agent. Reference task IDs.")],
    ) -> str:
        """Dispatch the logistics agent to work on transportation, timing, and scheduling tasks."""
        return await run_agent(
            "logistics", message, task_ids,
            self._chat_client, self._task_board, self._document, self._emitter,
        )

    @tool
    async def call_sightseeing_agent(
        self,
        task_ids: Annotated[list[int], Field(description="Task IDs for the sightseeing agent to work on")],
        message: Annotated[str, Field(description="Brief instruction for the sightseeing agent. Reference task IDs.")],
    ) -> str:
        """Dispatch the sightseeing agent to work on landmarks, museums, and walking route tasks."""
        return await run_agent(
            "sightseeing", message, task_ids,
            self._chat_client, self._task_board, self._document, self._emitter,
        )

    @tool
    async def call_experience_agent(
        self,
        task_ids: Annotated[list[int], Field(description="Task IDs for the experience agent to work on")],
        message: Annotated[str, Field(description="Brief instruction for the experience agent. Reference task IDs.")],
    ) -> str:
        """Dispatch the experience agent to work on events, activities, and nightlife tasks."""
        return await run_agent(
            "experience", message, task_ids,
            self._chat_client, self._task_board, self._document, self._emitter,
        )

    @tool
    async def call_food_agent(
        self,
        task_ids: Annotated[list[int], Field(description="Task IDs for the food & drinks agent to work on")],
        message: Annotated[str, Field(description="Brief instruction for the food agent. Reference task IDs.")],
    ) -> str:
        """Dispatch the food & drinks agent to work on restaurant, bar, and cuisine tasks."""
        return await run_agent(
            "food", message, task_ids,
            self._chat_client, self._task_board, self._document, self._emitter,
        )

    @property
    def all(self) -> list:
        return [
            self.call_logistics_agent,
            self.call_sightseeing_agent,
            self.call_experience_agent,
            self.call_food_agent,
        ]


async def run_workflow(
    user_message: str,
    chat_client: AzureOpenAIChatClient,
    emitter: EventEmitter,
) -> None:
    """Run the full multi-agent travel planning workflow.

    1. Create shared scratchpads
    2. Build the facilitator agent with all tools
    3. Let the facilitator orchestrate the specialists
    4. Stream events to the frontend via the emitter
    """
    # Shared state
    task_board = TaskBoard()
    document = SharedDocument()

    # Build tools
    facilitator_tools = FacilitatorTools(task_board, document, emitter)
    dispatcher = AgentDispatcher(chat_client, task_board, document, emitter)

    all_tools = facilitator_tools.all + dispatcher.all

    # Load facilitator prompt
    template = _jinja_env.get_template("facilitator.j2")
    facilitator_prompt = template.render().strip()

    # Create the facilitator agent
    facilitator = Agent(
        client=chat_client,
        name="Facilitator",
        instructions=facilitator_prompt,
        tools=all_tools,
    )

    # Run the facilitator
    thread = AgentThread(message_store=ChatMessageStore(messages=[]))

    await emitter.emit("workflow_started", {"message": user_message})

    try:
        full_response: list[str] = []
        # Buffer for accumulating facilitator text between tool-call boundaries
        text_buffer: list[str] = []
        # Track call_id -> tool_name for matching results to calls
        call_id_map: dict[str, str] = {}
        # Track which call_ids we've already seen (to flush text on first chunk)
        seen_call_ids: set[str] = set()

        async for update in facilitator.run(user_message, stream=True, thread=thread):
            if update.text:
                full_response.append(update.text)
                text_buffer.append(update.text)

            # Emit facilitator tool calls for the UI
            for content in (update.contents or []):
                ctype = getattr(content, "type", "")

                if ctype == "function_call":
                    tool_name = getattr(content, "name", None) or ""
                    call_id = getattr(content, "call_id", None) or ""

                    # Accumulate the best-known name for this call_id
                    if call_id and tool_name:
                        call_id_map[call_id] = tool_name

                    # Flush accumulated text as a single message on the first
                    # chunk of a new tool call (only once per call_id)
                    if call_id and call_id not in seen_call_ids:
                        seen_call_ids.add(call_id)
                        if text_buffer:
                            segment = "".join(text_buffer)
                            text_buffer.clear()
                            await emitter.emit("facilitator_message", {
                                "agent": "facilitator",
                                "display_name": "Facilitator",
                                "content": segment.strip(),
                            })
                    # Don't emit start events during streaming — we emit
                    # a single combined event from function_result instead

                elif ctype == "function_result":
                    call_id = getattr(content, "call_id", None) or ""
                    tool_name = call_id_map.get(call_id, "unknown")
                    # Skip results from agent dispatch calls
                    if not tool_name.startswith("call_"):
                        result_str = str(getattr(content, "result", ""))
                        if len(result_str) > 500:
                            result_str = result_str[:500] + "..."
                        await emitter.emit("tool_call", {
                            "agent": "facilitator",
                            "tool": tool_name,
                            "result": result_str,
                            "phase": "complete",
                        })

        final_answer = "".join(full_response)
        await emitter.emit("final_answer", {"content": final_answer})

    except Exception as e:
        logger.error("Workflow error: %s", e, exc_info=True)
        await emitter.emit("error", {"message": str(e)})

    finally:
        # Send final state snapshot
        await emitter.emit("workflow_finished", {
            "tasks": task_board.to_dict_list(),
            "document_versions": document.list_versions(),
        })
        await emitter.done()
