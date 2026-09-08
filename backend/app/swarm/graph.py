"""Build + run the LangGraph Swarm.

Per run we open ONE stdio session to the FastMCP server (so a single subprocess
serves the whole run), load the MCP tools, wrap each in the healing executor,
build the three peer agents with explicit handoff tools, and execute.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph_swarm import create_swarm

from ..context import RunContext
from ..healing.executor import HealingExecutor
from ..llm import build_model
from ..stream import events
from .agents.detection import build_detection_agent
from .agents.extraction import build_extraction_agent
from .agents.posting import build_posting_agent

log = logging.getLogger("swarm.graph")

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "figma": {
                "command": sys.executable,
                "args": ["-m", "app.mcp_server.server"],
                "transport": "stdio",
                "cwd": str(_BACKEND_DIR),
                "env": dict(os.environ),
            }
        }
    )


async def execute_run(ctx: RunContext) -> None:
    """Drive one end-to-end swarm run, updating RunState + streaming events."""
    state = ctx.state
    await ctx.emit(events.run_started(ctx.run_id, state.run_number, state.file_key))
    state.status = "running"
    await ctx.checkpoint(10, "Change detection started")
    await ctx.agent_status("detection_agent", "active", "detect_changes")

    client = _mcp_client()
    try:
        async with client.session("figma") as session:
            # handle_tool_errors=False -> MCP tool errors RAISE (as ToolException)
            # instead of being swallowed into content, so the healing executor
            # can catch, classify, and self-heal them.
            raw_tools = await load_mcp_tools(session, handle_tool_errors=False)
            executor = HealingExecutor(ctx)
            tools_by_name = {t.name: executor.wrap(t) for t in raw_tools}

            model = build_model(ctx.settings)
            detection = build_detection_agent(model, tools_by_name, ctx)
            extraction = build_extraction_agent(model, tools_by_name, ctx)
            posting = build_posting_agent(model, tools_by_name, ctx)

            swarm = create_swarm(
                [detection, extraction, posting],
                default_active_agent="detection_agent",
            ).compile()

            task = HumanMessage(
                content=(
                    f"Start the Figma design-handoff run for file_key {state.file_key}. "
                    "Detect what changed, extract specs and an asset for the changed "
                    "frames, and post a developer-ready summary to Slack."
                )
            )
            await swarm.ainvoke({"messages": [task]}, config={"recursion_limit": 48})

        await _finalize(ctx)
    except Exception as exc:  # noqa: BLE001 — surface a clean run-level failure
        log.exception("run failed")
        state.status = "complete"
        root = _unwrap(exc)
        await ctx.emit(events.error(ctx.run_id, "swarm", type(root).__name__, str(root)[:400]))
        await ctx.emit(events.run_complete(ctx.run_id, "error"))
    finally:
        # session is already closed by the context manager; nothing to leak.
        pass


def _unwrap(exc: BaseException) -> BaseException:
    """Dig the root cause out of TaskGroup ExceptionGroups for a clear message."""
    seen = 0
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions and seen < 5:
        exc = exc.exceptions[0]
        seen += 1
    return exc


async def _finalize(ctx: RunContext) -> None:
    state = ctx.state
    if state.status not in ("no_changes",):
        state.status = "complete"
    # Persist the new snapshot so the NEXT run can diff against it.
    if state.current_version:
        all_frames = [
            {"id": f.id, "name": f.name, "hash": f.hash or ""}
            for f in (state.changed_frames + state.skipped_frames)
        ]
        if all_frames:
            await ctx.memory.save_snapshot(state.file_key, state.current_version, all_frames)
    await ctx.emit(events.run_complete(ctx.run_id, state.status))
