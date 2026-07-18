"""FastAPI application — REST + WebSocket surface for the swarm.

Run:  python -m app.main   (validates config, then serves on :8000)

Endpoints:
  POST /run          start a genuine end-to-end swarm run
  GET  /run/{id}     serialized RunState snapshot
  GET  /patterns     learned healing patterns (Part 4B memory)
  GET  /health       liveness + redacted config
  WS   /ws/run       live typed event stream for the dashboard
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import ConfigError, get_settings
from .context import RunContext
from .healing.memory import Memory
from .stream.websocket import EventBus, RunRegistry, run_ws_endpoint
from .swarm.graph import execute_run
from .swarm.state import RunState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)-14s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("swarm.api")


class RunRequest(BaseModel):
    file_key: Optional[str] = None


def create_app() -> FastAPI:
    app = FastAPI(title="Figma Design Handoff Swarm", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # demo dashboard on a different origin
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:
        try:
            settings = get_settings()  # fail fast on missing keys
        except ConfigError as exc:
            log.error("CONFIG ERROR: %s", exc)
            raise
        app.state.settings = settings
        app.state.bus = EventBus()
        app.state.registry = RunRegistry()
        app.state.memory = await Memory.open(settings.sqlite_path)
        app.state.tasks = set()
        # Seed run_number just past the highest run that taught us a pattern.
        patterns = await app.state.memory.list_patterns()
        seed = max((p["run_number_learned"] for p in patterns), default=0)
        app.state.run_counter = seed + 1
        log.info("startup OK · config=%s", settings.redacted())

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        for task in list(getattr(app.state, "tasks", ())):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        mem: Memory = getattr(app.state, "memory", None)
        if mem:
            await mem.close()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        settings = app.state.settings
        return {
            "status": "ok",
            "config": settings.redacted(),
            "active_runs": len(app.state.registry.all_ids()),
            "latest_run_id": app.state.registry.latest_run_id,
        }

    @app.post("/run")
    async def start_run(req: RunRequest) -> dict[str, Any]:
        settings = app.state.settings
        file_key = (req.file_key or settings.figma_file_key).strip()
        if not file_key:
            raise HTTPException(status_code=400, detail="file_key required")

        run_number = app.state.run_counter
        app.state.run_counter += 1
        state = RunState(run_number=run_number, file_key=file_key)
        app.state.registry.register(state)
        ctx = RunContext(
            state=state, bus=app.state.bus, memory=app.state.memory, settings=settings
        )

        task = asyncio.create_task(execute_run(ctx))
        app.state.tasks.add(task)
        task.add_done_callback(app.state.tasks.discard)

        return {"run_id": state.run_id, "run_number": run_number, "status": "started"}

    @app.get("/run/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        state = app.state.registry.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f"unknown run_id {run_id}")
        return state.snapshot()

    @app.get("/patterns")
    async def get_patterns() -> list[dict[str, Any]]:
        return await app.state.memory.list_patterns()

    @app.websocket("/ws/run")
    async def ws_run(websocket: WebSocket) -> None:
        await run_ws_endpoint(websocket, app.state.bus, app.state.registry)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # Validate config before booting so a missing key fails fast + clearly.
    try:
        get_settings()
    except ConfigError as exc:
        raise SystemExit(f"\n[config error] {exc}\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, log_level="info")
