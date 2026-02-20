# events.py
"""
SSE event types and emitter for streaming multi-agent workflow state to the frontend.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class SSEEvent:
    """Base SSE event."""
    event: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        return f"event: {self.event}\ndata: {json.dumps(self.data)}\n\n"


class EventEmitter:
    """Async queue-based event emitter for SSE streaming."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()

    async def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Emit an SSE event to the stream."""
        await self._queue.put(SSEEvent(event=event_type, data=data or {}))

    async def done(self) -> None:
        """Signal that the stream is complete."""
        await self._queue.put(None)

    async def stream(self):
        """Async generator that yields SSE-formatted strings."""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event.to_sse()
