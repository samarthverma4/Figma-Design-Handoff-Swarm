"""RunContext — per-run bundle passed to the healing executor, handoff tools,
and agent nodes. Ties together the mutable RunState, the event bus, persistent
memory, and structured logging so every layer emits to the same stream.
"""
from __future__ import annotations

import logging
from typing import Any

from .config import Settings
from .healing.memory import Memory
from .stream import events
from .stream.websocket import EventBus
from .swarm.state import RunState

log = logging.getLogger("swarm.run")


class RunContext:
    def __init__(self, *, state: RunState, bus: EventBus, memory: Memory, settings: Settings):
        self.state = state
        self.bus = bus
        self.memory = memory
        self.settings = settings

    @property
    def run_id(self) -> str:
        return self.state.run_id

    async def emit(self, event: dict[str, Any]) -> None:
        """Publish an event to the stream and log it (structured, one line)."""
        etype = event.get("type")
        log.info("event %-14s %s", etype, _concise(event))
        await self.bus.publish(event)

    async def checkpoint(self, pct: int, label: str) -> None:
        self.state.checkpoint = pct
        await self.emit(events.checkpoint(self.run_id, pct, label))

    async def set_status(self, status: str) -> None:
        self.state.status = status  # type: ignore[assignment]

    async def agent_status(self, agent: str, status: str, tool: str | None = None) -> None:
        await self.emit(events.agent_status(self.run_id, agent, status, tool))


def _concise(event: dict[str, Any]) -> str:
    skip = {"type", "run_id", "timestamp"}
    parts = []
    for k, v in event.items():
        if k in skip:
            continue
        text = str(v)
        if len(text) > 80:
            text = text[:77] + "..."
        parts.append(f"{k}={text}")
    return " ".join(parts)
