# tools.py
"""
Scratchpad tools for the multi-agent travel planning system.

Two tool sets:
- FacilitatorTools: create tasks, check status, dispatch agents, read document
- SpecialistTools: read/complete tasks, read/write document
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from pydantic import Field
from agent_framework import tool

from scratchpad import TaskBoard, SharedDocument
from events import EventEmitter

logger = logging.getLogger("travel.tools")


class SpecialistTools:
    """Tools available to specialist agents (logistics, sightseeing, experience, food)."""

    def __init__(self, task_board: TaskBoard, document: SharedDocument, emitter: EventEmitter, agent_name: str) -> None:
        self._task_board = task_board
        self._document = document
        self._emitter = emitter
        self._agent_name = agent_name

    @tool
    async def read_tasks(
        self,
        task_ids: Annotated[list[int], Field(description="List of task IDs to read from the task board")],
    ) -> str:
        """Read specific tasks from the shared task board to understand your assignments."""
        tasks = self._task_board.read_tasks(task_ids)
        if not tasks:
            return "No tasks found with the given IDs."
        result = []
        for t in tasks:
            status = "✅ Done" if t.finished else "⏳ Pending"
            result.append(f"Task {t.id} [{status}]: {t.text}")
        return "\n".join(result)

    @tool
    async def complete_task(
        self,
        task_id: Annotated[int, Field(description="ID of the task to mark as completed")],
    ) -> str:
        """Mark a task as completed on the shared task board."""
        task = self._task_board.complete_task(task_id)
        if task is None:
            return f"Task {task_id} not found."
        await self._emitter.emit("task_updated", {
            "id": task.id, "text": task.text,
            "assigned_to": task.assigned_to, "finished": True,
        })
        logger.info("Task %d completed by %s", task_id, self._agent_name)
        return f"Task {task_id} marked as completed."

    @tool
    async def read_document(self) -> str:
        """Read the current version of the shared travel plan document."""
        content = self._document.read_latest()
        if not content:
            return "The shared document is empty. No content has been written yet."
        return content

    @tool
    async def write_to_document(
        self,
        content: Annotated[str, Field(description="Your contribution to the travel plan. Write your recommendations placed into the itinerary timeline (e.g., morning/afternoon/evening blocks). This will be appended to the current document.")],
        change_description: Annotated[str, Field(description="Brief description of what you added (e.g., 'Added morning sightseeing recommendations for Day 1')")],
    ) -> str:
        """Add your contribution to the shared travel plan document. Your content will be appended to the existing document. Multiple agents write concurrently, so focus on YOUR expertise area only."""
        version = self._document.append(content, self._agent_name, change_description)
        await self._emitter.emit("document_updated", {
            "version": version.version,
            "author": version.author,
            "timestamp": version.timestamp,
            "change_description": version.change_description,
            "content": version.content,
        })
        logger.info("Document updated by %s: version %d", self._agent_name, version.version)
        return f"Contribution added to document (version {version.version}). Change: {change_description}"

    @property
    def all(self) -> list:
        return [self.read_tasks, self.complete_task, self.read_document, self.write_to_document]


class FacilitatorTools:
    """Tools for the facilitator agent to manage tasks and read the document."""

    def __init__(self, task_board: TaskBoard, document: SharedDocument, emitter: EventEmitter) -> None:
        self._task_board = task_board
        self._document = document
        self._emitter = emitter

    @tool
    async def create_tasks(
        self,
        tasks_json: Annotated[str, Field(description='JSON array of tasks. Each object needs "text" (task description) and "assigned_to" (agent name: logistics, sightseeing, experience, or food). Example: [{"text": "Find flights to Prague", "assigned_to": "logistics"}]')],
    ) -> str:
        """Create tasks on the shared task board and assign them to specialist agents."""
        logger.info("create_tasks called with type=%s, value=%s", type(tasks_json).__name__, repr(tasks_json)[:500])
        if isinstance(tasks_json, list):
            tasks = tasks_json
        elif isinstance(tasks_json, str):
            tasks = json.loads(tasks_json)
        else:
            tasks = json.loads(str(tasks_json))
        created = self._task_board.create_tasks(tasks)
        task_dicts = [
            {"id": t.id, "text": t.text, "assigned_to": t.assigned_to, "finished": False}
            for t in created
        ]
        await self._emitter.emit("tasks_created", {"tasks": task_dicts})
        logger.info("Created %d tasks on the task board", len(created))
        summary = "\n".join(f"  Task {t.id}: [{t.assigned_to}] {t.text}" for t in created)
        return f"Created {len(created)} tasks:\n{summary}"

    @tool
    async def get_plan_status(self) -> str:
        """Check the current status of all tasks on the task board."""
        tasks = self._task_board.get_all_tasks()
        if not tasks:
            return "No tasks on the task board yet."
        lines = []
        done_count = sum(1 for t in tasks if t.finished)
        for t in tasks:
            status = "✅" if t.finished else "⏳"
            lines.append(f"  {status} Task {t.id} [{t.assigned_to}]: {t.text}")
        lines.append(f"\nProgress: {done_count}/{len(tasks)} tasks completed.")
        if self._task_board.all_done():
            lines.append("All tasks are done! Ready to compose the final answer.")
        return "\n".join(lines)

    @tool
    async def read_document(self) -> str:
        """Read the current shared travel plan document compiled by all agents."""
        content = self._document.read_latest()
        if not content:
            return "The shared document is empty."
        version = self._document.get_latest_version_number()
        return f"[Document v{version}]\n\n{content}"

    @tool
    async def rewrite_document(self, content: str) -> str:
        """Rewrite the entire shared document. Use this ONLY in your final review step
        to merge and reorganize all agent contributions into a clean, unified itinerary.
        Do NOT use this during the planning phase — agents append their own contributions.

        Args:
            content: The complete, reorganized itinerary document.
        """
        self._document.write(content, author="facilitator", change_description="Final merge and reorganization of all agent contributions")
        version = self._document.get_latest_version_number()
        await self._emitter.emit("document_updated", {
            "version": version,
            "content": content,
            "author": "facilitator",
        })
        return f"Document rewritten (v{version}). Final merged itinerary saved."

    @property
    def all(self) -> list:
        return [self.create_tasks, self.get_plan_status, self.read_document, self.rewrite_document]
