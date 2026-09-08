"""FastMCP server — the single source of real Figma + Slack access.

Runnable as a stdio MCP server:  python -m app.mcp_server.server
The swarm (main process) launches this as a subprocess and loads these tools via
langchain-mcp-adapters, so the agents call *genuine* MCP tools.

Every tool makes a real API call. On a normalized FigmaAPIError we re-raise a
ToolError whose text begins with the error class name, so the healing executor
on the other side of the MCP boundary can re-classify it (RateLimitError,
NotFoundError, AuthError, MalformedResponseError, TransientServerError).
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..config import get_settings
from .errors import FigmaAPIError
from .figma_tools import FigmaClient, hash_frame
from .http_client import HttpClient
from .slack_tools import SlackClient

mcp = FastMCP("figma-handoff-swarm")

# Lazily-built, process-wide clients (one HttpClient per server process).
_http: HttpClient | None = None
_figma: FigmaClient | None = None
_slack: SlackClient | None = None


def _clients() -> tuple[FigmaClient, SlackClient]:
    global _http, _figma, _slack
    if _figma is None or _slack is None:
        settings = get_settings()
        # The HealingExecutor (main process) is the single retry authority, so the
        # transport layer here fails fast — no inner retry stacking on the heal loop.
        _http = HttpClient(
            timeout=settings.http_timeout_seconds,
            max_transport_retries=0,
            max_backoff=settings.retry_max_backoff_seconds,
        )
        _figma = FigmaClient(settings.figma_token, _http)
        _slack = SlackClient(settings.slack_bot_token, _http)
    return _figma, _slack


def _guard(exc: FigmaAPIError) -> ToolError:
    # Surface a signature-prefixed string; never leak tokens (none are in these).
    return ToolError(exc.as_tool_error())


# ─────────────────────────── Figma tools ────────────────────────────────────

@mcp.tool
async def get_file_metadata(file_key: str) -> dict[str, Any]:
    """Return name, last_modified, version, thumbnail_url for a Figma file."""
    figma, _ = _clients()
    try:
        return await figma.get_file_metadata(file_key)
    except FigmaAPIError as exc:
        raise _guard(exc) from exc


@mcp.tool
async def get_file_versions(file_key: str) -> list[dict[str, Any]]:
    """Return the version history (id, created_at, label, author handle)."""
    figma, _ = _clients()
    try:
        return await figma.get_file_versions(file_key)
    except FigmaAPIError as exc:
        raise _guard(exc) from exc


@mcp.tool
async def get_file_nodes(file_key: str, node_ids: list[str]) -> dict[str, Any]:
    """Return the full node tree for the given node ids."""
    figma, _ = _clients()
    try:
        return await figma.get_file_nodes(file_key, node_ids)
    except FigmaAPIError as exc:
        raise _guard(exc) from exc


@mcp.tool
async def get_frame_specs(file_key: str, node_id: str) -> dict[str, Any]:
    """Extract spacing/padding, color fills (hex), typography and layout mode
    for one frame. Falls back to bounding-box geometry when auto-layout data is
    absent."""
    figma, _ = _clients()
    try:
        return await figma.get_frame_specs(file_key, node_id)
    except FigmaAPIError as exc:
        raise _guard(exc) from exc


@mcp.tool
async def get_published_styles(file_key: str) -> dict[str, list[dict[str, Any]]]:
    """Return the file's color and text styles."""
    figma, _ = _clients()
    try:
        return await figma.get_published_styles(file_key)
    except FigmaAPIError as exc:
        raise _guard(exc) from exc


@mcp.tool
async def export_asset(
    file_key: str, node_id: str, fmt: str = "png", scale: float = 2.0
) -> dict[str, Any]:
    """Render a node to an image via the Figma image API, download the real
    bytes, persist them to the export directory, and return file metadata."""
    figma, _ = _clients()
    settings = get_settings()
    try:
        result = await figma.export_asset(file_key, node_id, fmt, scale)
    except FigmaAPIError as exc:
        raise _guard(exc) from exc

    image_bytes: bytes = result.pop("bytes")
    safe_node = node_id.replace(":", "-")
    filename = f"{safe_node}@{scale:g}x.{fmt}"
    out_path = Path(settings.asset_dir) / filename
    out_path.write_bytes(image_bytes)
    width, height = _png_dimensions(image_bytes)
    return {
        "node_id": node_id,
        "filename": filename,
        "path": str(out_path),
        "url": result["url"],
        "format": fmt,
        "scale": scale,
        "width": width,
        "height": height,
        "bytes_written": len(image_bytes),
    }


@mcp.tool
async def detect_changes(file_key: str) -> dict[str, Any]:
    """Change detection built on get_file_metadata + get_file_nodes.

    Compares each top-level frame's content hash against the previous run's
    snapshot (persisted in SQLite). Returns changed vs skipped frames and both
    version markers. On the first ever run there is no baseline, so every frame
    is reported as changed. Read-only: the snapshot is committed by the main
    process only after a run completes successfully.
    """
    from ..healing.memory import Memory  # local import: server owns its own DB handle
    from .figma_tools import enumerate_frame_nodes

    figma, _ = _clients()
    settings = get_settings()
    try:
        # Single request: metadata + full node tree (cheaper vs 3 calls).
        data = await figma.get_file_snapshot(file_key)
    except FigmaAPIError as exc:
        raise _guard(exc) from exc

    document = data.get("document") or {}
    version = str(data.get("version", ""))
    file_name = data.get("name")
    frame_nodes = enumerate_frame_nodes(document)

    memory = await Memory.open(settings.sqlite_path)
    try:
        prior = await memory.get_snapshot(file_key)
        last_version = await memory.get_last_version(file_key)
    finally:
        await memory.close()

    changed: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for node in frame_nodes:
        h = hash_frame(node)
        entry = {"id": node.get("id"), "name": node.get("name", "unnamed"), "hash": h}
        if not prior:  # first run: no baseline -> everything is "changed"
            changed.append(entry)
        elif prior.get(node.get("id")) != h:
            changed.append(entry)
        else:
            skipped.append(entry)

    return {
        "current_version": version,
        "last_known_version": last_version,
        "file_name": file_name,
        "total_frames": len(frame_nodes),
        "changed": changed,
        "skipped": skipped,
        "no_changes": bool(prior) and len(changed) == 0,
    }


# ─────────────────────────── Slack delivery tool ────────────────────────────

@mcp.tool
async def post_summary(destination: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Post a formatted summary to Slack. payload must contain 'text' and may
    contain 'blocks'. Returns the real message id + permalink as proof."""
    _, slack = _clients()
    settings = get_settings()
    if destination not in ("slack", ""):
        raise ToolError(f"unsupported destination '{destination}' (only 'slack' is configured)")
    try:
        return await slack.post_summary(settings.slack_channel_id, payload)
    except FigmaAPIError as exc:
        raise _guard(exc) from exc


def _png_dimensions(data: bytes) -> tuple[int | None, int | None]:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    return None, None


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
