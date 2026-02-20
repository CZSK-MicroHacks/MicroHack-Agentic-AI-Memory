# scratchpad.py
"""
Shared scratchpad memory for multi-agent coordination.

Two scratchpad types:
- TaskBoard: Task planning and tracking (facilitator creates, agents complete)
- SharedDocument: Collaborative document with version history
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone


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
class DocumentVersion:
    """A snapshot of the shared document at a point in time."""
    version: int
    content: str
    author: str
    timestamp: str
    change_description: str


class SharedDocument:
    """Versioned shared document that agents collaboratively build.

    Every write creates a new version by appending/integrating a contribution
    into the current document. Agents run concurrently, so each write reads
    the latest content at write-time and appends to it.
    """

    def __init__(self) -> None:
        self._versions: list[DocumentVersion] = []

    def read_latest(self) -> str:
        """Return the latest document content, or empty string if none."""
        if not self._versions:
            return ""
        return self._versions[-1].content

    def write(self, content: str, author: str, change_description: str = "") -> DocumentVersion:
        """Save a new version of the document by replacing it entirely."""
        if not change_description:
            change_description = f"{author} updated the document"

        version = DocumentVersion(
            version=len(self._versions) + 1,
            content=content,
            author=author,
            timestamp=datetime.now(timezone.utc).isoformat(),
            change_description=change_description,
        )
        self._versions.append(version)
        return version

    def append(self, contribution: str, author: str, change_description: str = "") -> DocumentVersion:
        """Append a contribution to the current document, creating a new version.

        This is safe for concurrent use — it reads the latest content at call
        time and appends the new contribution.
        """
        current = self.read_latest()
        if current:
            new_content = f"{current}\n\n{contribution}"
        else:
            new_content = contribution

        if not change_description:
            change_description = f"{author} added content to the document"

        version = DocumentVersion(
            version=len(self._versions) + 1,
            content=new_content,
            author=author,
            timestamp=datetime.now(timezone.utc).isoformat(),
            change_description=change_description,
        )
        self._versions.append(version)
        return version

    def get_version(self, version_number: int) -> DocumentVersion | None:
        """Get a specific historical version (1-based)."""
        idx = version_number - 1
        if 0 <= idx < len(self._versions):
            return self._versions[idx]
        return None

    def list_versions(self) -> list[dict]:
        """Return metadata for all versions."""
        return [
            {
                "version": v.version,
                "author": v.author,
                "timestamp": v.timestamp,
                "change_description": v.change_description,
            }
            for v in self._versions
        ]

    def get_latest_version_number(self) -> int:
        """Return the current version number (0 if empty)."""
        return len(self._versions)
