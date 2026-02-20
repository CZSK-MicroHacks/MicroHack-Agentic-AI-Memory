# scratchpad.py
"""
Shared scratchpad memory for multi-agent coordination.

Two scratchpad types:
- TaskBoard: Task planning and tracking (facilitator creates, agents complete)
- SharedDocument: Slot-based collaborative itinerary document
"""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class Task:
    """A single task on the task board."""
    id: int
    text: str
    assigned_to: str
    finished: bool = False


class TaskBoard:
    """Shared task board for multi-agent coordination.

    The facilitator creates tasks; specialist agents read and complete them.
    """

    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._next_id: int = 1

    def create_tasks(self, tasks: list[dict]) -> list[Task]:
        """Create multiple tasks. Each dict needs 'text' and 'assigned_to'."""
        created = []
        for t in tasks:
            task = Task(
                id=self._next_id,
                text=t["text"],
                assigned_to=t["assigned_to"],
            )
            self._tasks.append(task)
            self._next_id += 1
            created.append(task)
        return created

    def read_tasks(self, task_ids: list[int]) -> list[Task]:
        """Read specific tasks by their IDs."""
        id_set = set(task_ids)
        return [t for t in self._tasks if t.id in id_set]

    def complete_task(self, task_id: int) -> Task | None:
        """Mark a task as finished. Returns the updated task or None."""
        for t in self._tasks:
            if t.id == task_id:
                t.finished = True
                return t
        return None

    def get_all_tasks(self) -> list[Task]:
        """Return all tasks with current status."""
        return list(self._tasks)

    def all_done(self) -> bool:
        """Check if every task is finished."""
        return all(t.finished for t in self._tasks) if self._tasks else False

    def to_dict_list(self) -> list[dict]:
        """Serialize all tasks to dicts."""
        return [
            {"id": t.id, "text": t.text, "assigned_to": t.assigned_to, "finished": t.finished}
            for t in self._tasks
        ]


@dataclass
class SlotEntry:
    """A single agent's contribution to a day/time-slot."""
    agent: str
    content: str
    timestamp: str


# Valid time-slot identifiers in render order
TimeSlot = Literal["general", "morning", "afternoon", "evening", "night"]
SLOT_ORDER: list[TimeSlot] = ["general", "morning", "afternoon", "evening", "night"]
SLOT_LABELS: dict[TimeSlot, str] = {
    "general": "General",
    "morning": "Morning (9:00–12:00)",
    "afternoon": "Afternoon (12:00–18:00)",
    "evening": "Evening (18:00–22:00)",
    "night": "Night (22:00+)",
}


class SharedDocument:
    """Slot-based shared itinerary that agents collaboratively build.

    The document is organized as: day (int) → time_slot → list of entries.
    Day 0 is reserved for general info (airport transfer, accommodation, etc.).
    Agents write entries into specific slots concurrently.
    The facilitator can consolidate slots (replace all entries with a merged version)
    or rewrite a full day.

    A version counter tracks every mutation for the UI.
    """

    def __init__(self) -> None:
        # day -> time_slot -> list[SlotEntry]
        self._sections: dict[int, dict[TimeSlot, list[SlotEntry]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._version: int = 0
        self._history: list[dict] = []  # version metadata for UI

    # ── Specialist writes ────────────────────────────────────────────

    def write_section(
        self, day: int, time_slot: TimeSlot, content: str, agent: str,
    ) -> int:
        """Append an entry to a specific day/time-slot. Returns new version number."""
        entry = SlotEntry(
            agent=agent,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._sections[day][time_slot].append(entry)
        self._version += 1
        self._history.append({
            "version": self._version,
            "author": agent,
            "timestamp": entry.timestamp,
            "change_description": f"{agent} added to Day {day} / {time_slot}",
        })
        return self._version

    # ── Facilitator merges ───────────────────────────────────────────

    def consolidate_section(
        self, day: int, time_slot: TimeSlot, content: str, author: str = "facilitator",
    ) -> int:
        """Replace ALL entries in a day/time-slot with a single merged entry."""
        self._sections[day][time_slot] = [
            SlotEntry(
                agent=author,
                content=content,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        ]
        self._version += 1
        self._history.append({
            "version": self._version,
            "author": author,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "change_description": f"{author} consolidated Day {day} / {time_slot}",
        })
        return self._version

    # ── Reads ────────────────────────────────────────────────────────

    def render(self, show_agent_tags: bool = True) -> str:
        """Render the full document as markdown.

        If show_agent_tags=True, each entry is prefixed with [agent] so the
        facilitator can see who contributed what.
        """
        if not self._sections:
            return ""

        lines: list[str] = []
        for day_num in sorted(self._sections.keys()):
            slots = self._sections[day_num]
            if day_num == 0:
                lines.append("## General Info")
            else:
                lines.append(f"## Day {day_num}")
            lines.append("")

            for slot in SLOT_ORDER:
                entries = slots.get(slot, [])
                if not entries:
                    continue
                if slot != "general":
                    lines.append(f"### {SLOT_LABELS[slot]}")
                for entry in entries:
                    if show_agent_tags:
                        lines.append(f"**[{entry.agent}]**")
                    lines.append(entry.content)
                    lines.append("")

        return "\n".join(lines).strip()

    def read_latest(self) -> str:
        """Return the rendered document (with agent tags)."""
        return self.render(show_agent_tags=True)

    def render_clean(self) -> str:
        """Return the rendered document without agent tags (for final output)."""
        return self.render(show_agent_tags=False)

    def get_version(self) -> int:
        return self._version

    def list_versions(self) -> list[dict]:
        return list(self._history)

    def get_slot_entries(self, day: int, time_slot: TimeSlot) -> list[SlotEntry]:
        """Get raw entries for a specific slot."""
        return list(self._sections.get(day, {}).get(time_slot, []))
