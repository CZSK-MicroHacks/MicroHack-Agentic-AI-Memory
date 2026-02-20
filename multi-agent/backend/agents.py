# agents.py
"""
Specialist agent definitions for the multi-agent travel planning system.

Each specialist is a ChatAgent with scratchpad tools. The run_agent() function
executes a specialist and emits SSE events for the UI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import jinja2

from agent_framework import Agent, AgentThread, ChatMessageStore
from agent_framework.azure import AzureOpenAIChatClient

from scratchpad import TaskBoard, SharedDocument
from tools import SpecialistTools
from events import EventEmitter

logger = logging.getLogger("travel.agents")

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
)


def _load_prompt(template_name: str) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render().strip()


AGENT_CONFIGS = {
    "logistics": {"prompt_file": "logistics.j2", "display_name": "Logistics Agent"},
    "sightseeing": {"prompt_file": "sightseeing.j2", "display_name": "Sightseeing Agent"},
    "experience": {"prompt_file": "experience.j2", "display_name": "Experience Agent"},
    "food": {"prompt_file": "food.j2", "display_name": "Food & Drinks Agent"},
}


async def run_agent(
    agent_name: str,
    message: str,
    task_ids: list[int],
    chat_client: AzureOpenAIChatClient,
    task_board: TaskBoard,
    document: SharedDocument,
    emitter: EventEmitter,
) -> str:
    """Run a specialist agent and emit SSE events for the UI.

    Returns the agent's text response.
    """
    config = AGENT_CONFIGS.get(agent_name)
    if not config:
        return f"Unknown agent: {agent_name}"

    display_name = config["display_name"]
    logger.info("Starting %s for tasks %s", display_name, task_ids)

    await emitter.emit("agent_started", {
        "agent": agent_name,
        "display_name": display_name,
        "task_ids": task_ids,
        "message": message,
    })

    # Create specialist tools bound to this agent and its assigned tasks
    tools = SpecialistTools(task_board, document, emitter, agent_name, assigned_task_ids=task_ids)

    # Create the agent
    agent = Agent(
        client=chat_client,
        name=display_name,
        instructions=_load_prompt(config["prompt_file"]),
        tools=tools.all,
    )

    # Run in a fresh thread with the facilitator's message
    thread = AgentThread(message_store=ChatMessageStore(messages=[]))
    full_response: list[str] = []
    call_id_map: dict[str, str] = {}
    emitted_call_ids: set[str] = set()  # track which call_ids we already emitted start for

    async for update in agent.run(message, stream=True, thread=thread):
        if update.text:
            full_response.append(update.text)

        # Emit tool call events for the UI
        for content in (update.contents or []):
            ctype = getattr(content, "type", "")

            if ctype == "function_call":
                tool_name = getattr(content, "name", None) or ""
                call_id = getattr(content, "call_id", None) or ""
                # Accumulate the best-known name for this call_id
                if call_id and tool_name:
                    call_id_map[call_id] = tool_name
                # Skip — we emit a single start event from function_result
            elif ctype == "function_result":
                call_id = getattr(content, "call_id", None) or ""
                tool_name = call_id_map.get(call_id, "unknown")
                result_str = str(getattr(content, "result", ""))
                if len(result_str) > 500:
                    result_str = result_str[:500] + "..."
                # Emit a single combined event (start+end) for this tool call
                await emitter.emit("tool_call", {
                    "agent": agent_name,
                    "tool": tool_name,
                    "result": result_str,
                    "phase": "complete",
                })

    response_text = "".join(full_response)

    await emitter.emit("agent_message", {
        "agent": agent_name,
        "display_name": display_name,
        "content": response_text,
    })

    # Auto-complete any assigned tasks the agent forgot to mark done
    for tid in task_ids:
        tasks_check = task_board.read_tasks([tid])
        if tasks_check and not tasks_check[0].finished:
            logger.warning("%s did not complete task %d — auto-completing", display_name, tid)
            task_board.complete_task(tid)
            await emitter.emit("task_updated", {
                "id": tid, "text": tasks_check[0].text,
                "assigned_to": tasks_check[0].assigned_to, "finished": True,
            })

    await emitter.emit("agent_finished", {
        "agent": agent_name,
        "display_name": display_name,
    })

    logger.info("%s completed", display_name)
    return response_text
