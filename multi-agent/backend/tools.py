# tools.py
"""
Scratchpad tools for the multi-agent travel planning system.

Two tool sets:
- FacilitatorTools: create tasks, check status, read/consolidate document
- SpecialistTools: read/complete tasks, write sections to document
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal

from pydantic import Field
from agent_framework import tool

from scratchpad import TaskBoard, SharedDocument, SLOT_ORDER, SLOT_LABELS, TimeSlot
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
        """Read the current shared travel plan document to see what other agents have contributed."""
        content = self._document.read_latest()
        if not content:
            return "The shared document is empty. No content has been written yet."
        return content

    @tool
    async def write_section(
        self,
        day: Annotated[int, Field(description="Day number (1, 2, 3...). Use 0 for general info not tied to a specific day (e.g., airport transfer, accommodation, transit passes).")],
        time_slot: Annotated[Literal["general", "morning", "afternoon", "evening", "night"], Field(description="Time slot within the day. Use 'general' for day-level info, 'morning' for 9-12, 'afternoon' for 12-18, 'evening' for 18-22, 'night' for 22+.")],
        content: Annotated[str, Field(description="Your recommendations for this time slot as markdown bullet points. Only write YOUR expertise area. Be specific with timing, names, and practical details.")],
    ) -> str:
        """Write your recommendations into a specific day and time slot of the shared itinerary.

        Multiple agents can write to the same slot — entries are collected as candidates.
        The facilitator will merge them later. Focus on YOUR expertise only.
        """
        version = self._document.write_section(day, time_slot, content, self._agent_name)
        rendered = self._document.render(show_agent_tags=True)
        await self._emitter.emit("document_updated", {
            "version": version,
            "author": self._agent_name,
            "content": rendered,
            "change_description": f"{self._agent_name} added to Day {day} / {time_slot}",
        })
        logger.info("Document updated by %s: Day %d / %s (v%d)", self._agent_name, day, time_slot, version)
        return f"Written to Day {day} / {time_slot} (document v{version})."

    @property
    def all(self) -> list:
        return [self.read_tasks, self.complete_task, self.read_document, self.write_section]


class FacilitatorTools:
    """Tools for the facilitator agent to manage tasks and read/consolidate the document."""

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
        try:
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
        except Exception as e:
            logger.error("create_tasks FAILED: %s", e, exc_info=True)
            raise

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
        """Read the current shared itinerary with agent tags showing who contributed each entry."""
        content = self._document.read_latest()
        if not content:
            return "The shared document is empty."
        version = self._document.get_version()
        return f"[Document v{version}]\n\n{content}"

    @tool
    async def consolidate_section(
        self,
        day: Annotated[int, Field(description="Day number (0 for general info, 1+ for specific days)")],
        time_slot: Annotated[Literal["general", "morning", "afternoon", "evening", "night"], Field(description="Time slot to consolidate")],
        content: Annotated[str, Field(description="The merged, clean content for this slot — combining the best from all agent contributions into a unified narrative with specific times, places, and practical details.")],
    ) -> str:
        """Merge all agent contributions for a specific day/time-slot into a single clean entry.

        Use this after agents have finished to resolve duplicate or conflicting entries
        within a slot. Replaces ALL existing entries in that slot with your merged version.
        """
        version = self._document.consolidate_section(day, time_slot, content)
        rendered = self._document.render(show_agent_tags=False)
        await self._emitter.emit("document_updated", {
            "version": version,
            "author": "facilitator",
            "content": rendered,
            "change_description": f"Consolidated Day {day} / {time_slot}",
        })
        logger.info("Facilitator consolidated Day %d / %s (v%d)", day, time_slot, version)
        return f"Consolidated Day {day} / {time_slot} (document v{version})."

    @tool
    async def read_document_clean(self) -> str:
        """Read the document without agent tags — use this to preview the final output."""
        content = self._document.render_clean()
        if not content:
            return "The shared document is empty."
        return content

    @property
    def all(self) -> list:
        return [self.create_tasks, self.get_plan_status, self.read_document, self.consolidate_section, self.read_document_clean]
