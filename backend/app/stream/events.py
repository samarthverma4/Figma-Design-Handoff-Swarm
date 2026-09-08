"""Typed JSON events the dashboard consumes (Part 5).

Each builder returns a plain dict with a stable ``type`` plus ``run_id`` and a
``timestamp`` (epoch seconds). The frontend switches on ``type``.
"""
from __future__ import annotations

import time
from typing import Any


def _base(run_id: str, etype: str) -> dict[str, Any]:
    return {"type": etype, "run_id": run_id, "timestamp": time.time()}


def checkpoint(run_id: str, pct: int, label: str) -> dict[str, Any]:
    return {**_base(run_id, "checkpoint"), "pct": pct, "label": label}


def agent_status(run_id: str, agent: str, status: str, current_tool: str | None = None) -> dict[str, Any]:
    return {**_base(run_id, "agent_status"), "agent": agent, "status": status, "current_tool": current_tool}


def handoff(run_id: str, from_agent: str, to_agent: str, payload_summary: str, reason: str) -> dict[str, Any]:
    return {
        **_base(run_id, "handoff"),
        "from_agent": from_agent,
        "to_agent": to_agent,
        "payload_summary": payload_summary,
        "reason": reason,
    }


def cursor_action(run_id: str, target: str, action: str, caption: str,
                  x: float | None = None, y: float | None = None) -> dict[str, Any]:
    """Emitted immediately before the corresponding real tool call so the ghost
    cursor tracks genuine agent work. x/y are optional 0..100 viewport hints."""
    return {**_base(run_id, "cursor_action"), "target": target, "action": action,
            "caption": caption, "x": x, "y": y}


def spec_extracted(run_id: str, frame: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {**_base(run_id, "spec_extracted"), "frame": frame, "spec": spec}


def asset_exported(run_id: str, filename: str, dimensions: str, url: str | None) -> dict[str, Any]:
    return {**_base(run_id, "asset_exported"), "filename": filename, "dimensions": dimensions, "url": url}


def error(run_id: str, tool: str, error_type: str, message: str) -> dict[str, Any]:
    return {**_base(run_id, "error"), "tool": tool, "error_type": error_type, "message": message}


def healing(run_id: str, stage: str, strategy: str, outcome: str,
            tool: str | None = None, attempt: int | None = None) -> dict[str, Any]:
    return {**_base(run_id, "healing"), "stage": stage, "strategy": strategy,
            "outcome": outcome, "tool": tool, "attempt": attempt}


def pattern_matched(run_id: str, pattern_id: int, resolution: str) -> dict[str, Any]:
    return {**_base(run_id, "pattern_matched"), "pattern_id": pattern_id, "resolution": resolution}


def delivery(run_id: str, destination: str, message_url: str | None, status: str) -> dict[str, Any]:
    return {**_base(run_id, "delivery"), "destination": destination,
            "message_url": message_url, "status": status}


def run_started(run_id: str, run_number: int, file_key: str) -> dict[str, Any]:
    return {**_base(run_id, "run_started"), "run_number": run_number, "file_key": file_key}


def run_complete(run_id: str, status: str) -> dict[str, Any]:
    return {**_base(run_id, "run_complete"), "status": status}
