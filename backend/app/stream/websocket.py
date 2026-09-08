"""In-memory event bus + WebSocket endpoint + run registry.

The bus is a simple async pub/sub keyed by run_id (plus a wildcard "*" stream so
a dashboard can follow whichever run is active). Every event is also retained in
a per-run history so a client that connects mid-run replays what it missed.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

from ..swarm.state import RunState

log = logging.getLogger("swarm.stream")

WILDCARD = "*"
_MAX_HISTORY = 500


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}

    async def publish(self, event: dict[str, Any]) -> None:
        run_id = event.get("run_id", WILDCARD)
        self._history.setdefault(run_id, []).append(event)
        if len(self._history[run_id]) > _MAX_HISTORY:
            self._history[run_id] = self._history[run_id][-_MAX_HISTORY:]
        for key in (run_id, WILDCARD):
            for q in list(self._subs.get(key, ())):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:  # pragma: no cover - slow consumer
                    pass

    def subscribe(self, run_id: str = WILDCARD) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subs.setdefault(run_id, set()).add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        self._subs.get(run_id, set()).discard(q)

    def history(self, run_id: str) -> list[dict[str, Any]]:
        return list(self._history.get(run_id, ()))


class RunRegistry:
    """Holds RunState snapshots by run_id so GET /run/{id} can serve them."""

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self.latest_run_id: Optional[str] = None

    def register(self, state: RunState) -> None:
        self._runs[state.run_id] = state
        self.latest_run_id = state.run_id

    def get(self, run_id: str) -> Optional[RunState]:
        return self._runs.get(run_id)

    def all_ids(self) -> list[str]:
        return list(self._runs.keys())


async def run_ws_endpoint(websocket: WebSocket, bus: EventBus, registry: RunRegistry) -> None:
    """WebSocket handler for /ws/run. Optional ?run_id= filters to one run;
    otherwise follows all runs (wildcard)."""
    await websocket.accept()
    requested = websocket.query_params.get("run_id")
    channel = requested or WILDCARD
    q = bus.subscribe(channel)
    try:
        # Replay history so a late subscriber is consistent.
        replay_id = requested or registry.latest_run_id
        if replay_id:
            for event in bus.history(replay_id):
                await websocket.send_json(event)
        while True:
            event = await q.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("ws error: %s", exc)
    finally:
        bus.unsubscribe(channel, q)
