"""Healing executor (Part 4A + hook into 4B).

Wraps every raw MCP tool in a resilient async executor that:
  1. emits a cursor_action immediately BEFORE the real tool call (so the ghost
     cursor tracks genuine work), plus agent_status;
  2. proactively applies a learned pattern if one exists for this tool
     (pattern_matched event + learned_patterns_applied);
  3. runs the call inside a capped retry loop, selecting a corrective strategy
     per normalized error type and emitting error/healing events for every
     attempt, diagnosis, strategy and outcome;
  4. on success, mutates RunState from the structured result and emits the
     relevant success event (spec_extracted / asset_exported / delivery / ...);
  5. on exhaustion, degrades gracefully — records the failure, marks the item
     incomplete, and returns an error string so the swarm continues with
     partial results instead of aborting.
Successful in-run heals are written back to the pattern store for future runs.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.tools import StructuredTool

from ..context import RunContext
from ..mcp_server.errors import classify_error_string
from ..stream import checkpoints, events
from ..swarm.state import (
    AssetRef,
    ColorSpec,
    ErrorRecord,
    FrameRef,
    FrameSpec,
    HealingEvent,
    TypographySpec,
)
from .strategies import strategy_for

log = logging.getLogger("swarm.healing")

# tool -> (target, action, caption, x, y) for the ghost cursor.
_CURSOR_MAP: dict[str, tuple[str, str, str, float, float]] = {
    "get_file_metadata": ("layers_panel", "scan", "Change Detection → reading file metadata", 20, 22),
    "get_file_versions": ("layers_panel", "scan", "Change Detection → scanning file versions", 20, 28),
    "get_file_nodes": ("layers_panel", "inspect", "Change Detection → inspecting nodes", 16, 34),
    "detect_changes": ("layers_panel", "diff", "Change Detection → diffing against last snapshot", 14, 30),
    "get_frame_specs": ("properties_inspector", "read", "Extraction → reading spacing / color / type", 84, 46),
    "get_published_styles": ("properties_inspector", "read", "Extraction → reading published styles", 84, 60),
    "export_asset": ("canvas_icon", "export", "Extraction → exporting asset", 52, 58),
    "post_summary": ("delivery", "post", "Posting → composing summary", 50, 88),
}

_AGENT_BY_TOOL: dict[str, str] = {
    "get_file_metadata": "detection_agent",
    "get_file_versions": "detection_agent",
    "get_file_nodes": "detection_agent",
    "detect_changes": "detection_agent",
    "get_frame_specs": "extraction_agent",
    "get_published_styles": "extraction_agent",
    "export_asset": "extraction_agent",
    "post_summary": "posting_agent",
}


class HealingExecutor:
    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.max_retries = ctx.settings.max_tool_retries

    def wrap(self, raw: StructuredTool) -> StructuredTool:
        """Return a new StructuredTool that routes calls through healing."""
        name = raw.name

        async def _run(**kwargs: Any) -> Any:
            return await self._execute(raw, name, kwargs)

        return StructuredTool(
            name=name,
            description=raw.description,
            args_schema=raw.args_schema,
            coroutine=_run,
        )

    async def _execute(self, raw: StructuredTool, name: str, kwargs: dict[str, Any]) -> Any:
        ctx = self.ctx
        agent = _AGENT_BY_TOOL.get(name, "agent")

        # (1) cursor + status BEFORE the real call.
        target, action, caption, x, y = _CURSOR_MAP.get(
            name, ("canvas", "act", f"{agent} → {name}", 50, 50)
        )
        await ctx.emit(events.cursor_action(ctx.run_id, target, action, caption, x, y))
        await ctx.agent_status(agent, "active", name)

        # (2) proactive learned-pattern application.
        kwargs = await self._apply_known_pattern(name, kwargs)

        if name == "post_summary":
            await ctx.checkpoint(90, checkpoints.label_for(90, destination=ctx.settings.delivery_destination))

        # (3) capped retry loop with per-error strategy.
        attempt = 0
        last_error_code = None
        while True:
            attempt += 1
            try:
                raw_result = await raw.ainvoke(kwargs)
                result = _coerce(raw_result)
                if attempt > 1:
                    await self._on_recovered(name, last_error_code, attempt)
                await self._on_success(name, result)
                return result
            except Exception as exc:  # noqa: BLE001 — normalize everything
                code = classify_error_string(str(exc))
                last_error_code = code
                await ctx.emit(events.error(ctx.run_id, name, code, _clean(str(exc))))
                ctx.state.errors.append(ErrorRecord(tool=name, error_type=code, message=_clean(str(exc))))
                strat = strategy_for(code)

                exhausted = attempt > self.max_retries
                if strat is None or not strat.recoverable or exhausted:
                    return await self._degrade(name, code, strat, attempt, str(exc))

                # emit healing(retrying) and prepare the next attempt.
                await ctx.set_status("self_healing")
                await ctx.agent_status(agent, "error", name)
                await ctx.emit(
                    events.healing(ctx.run_id, stage="diagnose", strategy=strat.name,
                                   outcome="retrying", tool=name, attempt=attempt)
                )
                ctx.state.healing_events.append(
                    HealingEvent(tool=name, attempt=attempt, diagnosis=strat.diagnosis,
                                 strategy=strat.name, outcome="retrying", error_type=code)
                )
                kwargs = await strat.prepare(attempt, kwargs)

    # ---- pattern memory ---------------------------------------------------

    async def _apply_known_pattern(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        patterns = [p for p in await self.ctx.memory.list_patterns() if p["tool_name"] == name]
        if not patterns:
            return kwargs
        # apply the most-exercised known fix proactively.
        pattern = max(patterns, key=lambda p: p["times_applied"])
        strat = strategy_for(pattern["error_signature"].split(":")[0])
        await self.ctx.memory.mark_pattern_applied(pattern["id"])
        self.ctx.state.learned_patterns_applied.append(pattern["resolution_strategy"])
        await self.ctx.emit(
            events.pattern_matched(self.ctx.run_id, pattern["id"], pattern["resolution_strategy"])
        )
        await self.ctx.emit(
            events.healing(self.ctx.run_id, stage="proactive", strategy=pattern["resolution_strategy"],
                           outcome="pre_applied", tool=name)
        )
        if strat and strat.recoverable:
            kwargs = await strat.prepare(0, kwargs)
        return kwargs

    async def _on_recovered(self, name: str, code: str | None, attempt: int) -> None:
        ctx = self.ctx
        strat = strategy_for(code or "")
        await ctx.emit(
            events.healing(ctx.run_id, stage="verify", strategy=strat.name if strat else "retry",
                           outcome="recovered", tool=name, attempt=attempt)
        )
        ctx.state.healing_events.append(
            HealingEvent(tool=name, attempt=attempt,
                         diagnosis=strat.diagnosis if strat else "recovered on retry",
                         strategy=strat.name if strat else "retry", outcome="recovered", error_type=code)
        )
        await ctx.set_status("running")
        # write the learned pattern back so future runs inherit it (Part 4B).
        if code and strat:
            await ctx.memory.record_pattern(
                run_number=ctx.state.run_number,
                tool_name=name,
                error_signature=f"{code}:{name}",
                diagnosis=strat.diagnosis,
                resolution_strategy=strat.name,
            )

    async def _degrade(self, name: str, code: str, strat, attempt: int, raw_msg: str) -> str:
        ctx = self.ctx
        await ctx.emit(
            events.healing(ctx.run_id, stage="exhausted",
                           strategy=strat.name if strat else "none",
                           outcome="degraded" if (strat and strat.recoverable) else "failed",
                           tool=name, attempt=attempt)
        )
        ctx.state.healing_events.append(
            HealingEvent(tool=name, attempt=attempt,
                         diagnosis=strat.diagnosis if strat else "no strategy for error",
                         strategy=strat.name if strat else "none",
                         outcome="degraded" if (strat and strat.recoverable) else "failed",
                         error_type=code)
        )
        # graceful degradation: return an error string so the agent keeps going.
        return (
            f"TOOL_DEGRADED({name}): {code} persisted after {attempt} attempt(s). "
            f"Continuing the run with partial results; this item is marked incomplete. "
            f"detail={_clean(raw_msg)}"
        )

    # ---- success side-effects: mutate state + emit ------------------------

    async def _on_success(self, name: str, result: Any) -> None:
        ctx = self.ctx
        handler: Callable | None = {
            "detect_changes": self._after_detect,
            "get_frame_specs": self._after_specs,
            "export_asset": self._after_export,
            "post_summary": self._after_post,
        }.get(name)
        if handler:
            await handler(result)

    async def _after_detect(self, result: Any) -> None:
        ctx = self.ctx
        if not isinstance(result, dict):
            return
        ctx.state.current_version = result.get("current_version")
        ctx.state.last_known_version = result.get("last_known_version")
        ctx.state.file_name = result.get("file_name")
        ctx.state.changed_frames = [FrameRef(**f) for f in result.get("changed", [])]
        ctx.state.skipped_frames = [FrameRef(**f) for f in result.get("skipped", [])]
        n = len(ctx.state.changed_frames)
        # No-op success path: explicit no_changes, OR nothing changed / empty file.
        if result.get("no_changes") or n == 0:
            ctx.state.status = "no_changes"
            await ctx.checkpoint(100, checkpoints.NO_CHANGES_LABEL)
        else:
            await ctx.checkpoint(30, checkpoints.label_for(30, n=n))

    async def _after_specs(self, result: Any) -> None:
        ctx = self.ctx
        if not isinstance(result, dict) or not result.get("node_id"):
            return
        node_id = result["node_id"]
        if any(s.node_id == node_id for s in ctx.state.extracted_specs):
            return  # dedupe: already extracted this node in this run
        spec = FrameSpec(
            node_id=node_id,
            name=result.get("name", node_id),
            type=result.get("type"),
            spacing=result.get("spacing", {}),
            colors=[ColorSpec(**c) for c in result.get("colors", [])],
            typography=[TypographySpec(**t) for t in result.get("typography", [])],
            incomplete=(result.get("spacing", {}).get("source") == "bounding_box_fallback"),
        )
        ctx.state.extracted_specs.append(spec)
        await ctx.emit(events.spec_extracted(ctx.run_id, spec.name, spec.model_dump(mode="json")))

    async def _after_export(self, result: Any) -> None:
        ctx = self.ctx
        if not isinstance(result, dict) or not result.get("filename"):
            return
        asset = AssetRef(
            node_id=result.get("node_id", ""),
            filename=result["filename"],
            path=result.get("path", ""),
            url=result.get("url"),
            width=result.get("width"),
            height=result.get("height"),
        )
        if any(a.node_id == asset.node_id for a in ctx.state.exported_assets):
            return
        ctx.state.exported_assets.append(asset)
        await ctx.emit(events.asset_exported(ctx.run_id, asset.filename, asset.dimensions, asset.url))

    async def _after_post(self, result: Any) -> None:
        ctx = self.ctx
        if not isinstance(result, dict):
            return
        ctx.state.delivery_result = result
        await ctx.emit(
            events.delivery(ctx.run_id, ctx.settings.delivery_destination,
                            result.get("permalink"), "delivered" if result.get("ok") else "failed")
        )
        # idempotency record + final checkpoint.
        if result.get("ok") and ctx.state.current_version:
            await ctx.memory.record_post(
                ctx.state.file_key, ctx.state.current_version,
                result.get("message_id"), result.get("permalink"),
            )
        await ctx.checkpoint(100, checkpoints.label_for(100))


def _coerce(raw_result: Any) -> Any:
    """Normalize a langchain-mcp-adapters tool result to a Python object.

    On success the adapter returns a list of MCP content blocks, e.g.
    ``[{"type": "text", "text": "<json>"}]`` (the clean dict lives in a separate
    artifact we don't receive via ainvoke). So we pull the text out and parse it.
    """
    if isinstance(raw_result, dict):
        return raw_result
    if isinstance(raw_result, list):
        texts = [
            b.get("text")
            for b in raw_result
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
        ]
        if texts:
            joined = texts[0] if len(texts) == 1 else "".join(texts)
            try:
                return json.loads(joined)
            except (ValueError, TypeError):
                return joined
        return raw_result
    if isinstance(raw_result, str):
        try:
            return json.loads(raw_result)
        except (ValueError, TypeError):
            return raw_result
    # ToolMessage-like objects expose .content
    content = getattr(raw_result, "content", None)
    if content is not None:
        return _coerce(content)
    return raw_result


def _clean(msg: str) -> str:
    return (msg or "").strip().replace("\n", " ")[:400]
