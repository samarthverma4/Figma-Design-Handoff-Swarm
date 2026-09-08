"""Real Figma REST API operations.

Every function here makes a genuine authenticated call to api.figma.com and
returns structured, typed output. Failures raise the normalized typed errors
from errors.py — nothing is swallowed.

The FastMCP server (server.py) wraps these as MCP tools; the change-detection
agent path also uses FigmaClient.list_frames / hash_frame directly to compute a
real diff against the previous run's snapshot.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import MalformedResponseError, NotFoundError
from .http_client import HttpClient

FIGMA_API = "https://api.figma.com/v1"

# Node types we treat as top-level "frames" for change detection / handoff.
_FRAME_TYPES = {"FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE", "SECTION", "SLIDE", "GROUP"}


def _headers(token: str) -> dict[str, str]:
    return {"X-Figma-Token": token}


def rgba_to_hex(color: dict[str, Any]) -> str:
    def ch(v: float) -> int:
        return max(0, min(255, round(float(v) * 255)))

    return "#{:02X}{:02X}{:02X}".format(ch(color.get("r", 0)), ch(color.get("g", 0)), ch(color.get("b", 0)))


class FigmaClient:
    """Authenticated Figma REST client. Token is never logged."""

    def __init__(self, token: str, http: HttpClient):
        self._token = token
        self._http = http

    # ---- Raw REST operations (1:1 with MCP tools) --------------------------

    async def get_file_metadata(self, file_key: str) -> dict[str, Any]:
        data = await self._http.request_json(
            "GET", f"{FIGMA_API}/files/{file_key}",
            tool="get_file_metadata", headers=_headers(self._token), params={"depth": 1},
        )
        return {
            "name": data.get("name"),
            "last_modified": data.get("lastModified"),
            "version": str(data.get("version", "")),
            "thumbnail_url": data.get("thumbnailUrl"),
        }

    async def get_file_versions(self, file_key: str) -> list[dict[str, Any]]:
        data = await self._http.request_json(
            "GET", f"{FIGMA_API}/files/{file_key}/versions",
            tool="get_file_versions", headers=_headers(self._token),
        )
        versions = data.get("versions")
        if not isinstance(versions, list):
            raise MalformedResponseError("versions list missing", tool="get_file_versions")
        return [
            {
                "id": str(v.get("id")),
                "created_at": v.get("created_at"),
                "label": v.get("label"),
                "description": v.get("description"),
                "user": (v.get("user") or {}).get("handle"),
            }
            for v in versions
        ]

    async def get_file_nodes(self, file_key: str, node_ids: list[str]) -> dict[str, Any]:
        if not node_ids:
            return {"nodes": {}}
        data = await self._http.request_json(
            "GET", f"{FIGMA_API}/files/{file_key}/nodes",
            tool="get_file_nodes", headers=_headers(self._token),
            params={"ids": ",".join(node_ids)},
        )
        nodes = data.get("nodes")
        if not isinstance(nodes, dict):
            raise MalformedResponseError("nodes map missing", tool="get_file_nodes")
        return {"nodes": nodes}

    async def get_published_styles(self, file_key: str) -> dict[str, list[dict[str, Any]]]:
        """Color + text styles referenced by the file.

        Reads the ``styles`` map from the full file JSON (real data, no mock).
        Distinguishes FILL styles (colors) from TEXT styles.
        """
        data = await self._http.request_json(
            "GET", f"{FIGMA_API}/files/{file_key}",
            tool="get_published_styles", headers=_headers(self._token), params={"depth": 1},
        )
        styles = data.get("styles") or {}
        colors: list[dict[str, Any]] = []
        text: list[dict[str, Any]] = []
        for style_id, meta in styles.items():
            entry = {
                "style_id": style_id,
                "name": meta.get("name"),
                "description": meta.get("description"),
            }
            stype = (meta.get("styleType") or "").upper()
            if stype == "FILL":
                colors.append(entry)
            elif stype == "TEXT":
                text.append(entry)
        return {"colors": colors, "text": text}

    async def export_asset(
        self, file_key: str, node_id: str, fmt: str = "png", scale: float = 2.0
    ) -> dict[str, Any]:
        """Ask Figma to render node_id and return the real image URL + bytes."""
        data = await self._http.request_json(
            "GET", f"{FIGMA_API}/images/{file_key}",
            tool="export_asset", headers=_headers(self._token),
            params={"ids": node_id, "format": fmt, "scale": scale},
        )
        images = data.get("images") or {}
        url = images.get(node_id)
        if not url:
            raise NotFoundError(
                f"Figma returned no image URL for node {node_id} (err={data.get('err')})",
                tool="export_asset",
            )
        image_bytes = await self._http.request_bytes("GET", url, tool="export_asset")
        return {"node_id": node_id, "format": fmt, "scale": scale, "url": url, "bytes": image_bytes}

    # ---- Derived operations -----------------------------------------------

    async def get_frame_specs(self, file_key: str, node_id: str) -> dict[str, Any]:
        """Extract spacing/padding, color fills (hex+token), typography, layout.

        Fallback path (MalformedResponse healing): when auto-layout metadata is
        absent (layoutMode == NONE / null spacing), spacing is derived from the
        node's absoluteBoundingBox instead of returning nothing.
        """
        result = await self.get_file_nodes(file_key, [node_id])
        wrapper = result["nodes"].get(node_id)
        if not wrapper or "document" not in wrapper:
            raise NotFoundError(f"node {node_id} not present in file", tool="get_frame_specs")
        node = wrapper["document"]
        return parse_frame_specs(node)

    async def get_file_snapshot(self, file_key: str) -> dict[str, Any]:
        """Fetch the whole file once (metadata + full node tree) in a single
        request. Used by change detection to avoid 3 separate API calls (cheaper
        against Figma's cost-based rate limits)."""
        return await self._http.request_json(
            "GET", f"{FIGMA_API}/files/{file_key}",
            tool="detect_changes", headers=_headers(self._token),
        )

    async def list_frames(self, file_key: str) -> list[dict[str, str]]:
        """Enumerate top-level frames (real structure from file JSON, depth=2)."""
        data = await self._http.request_json(
            "GET", f"{FIGMA_API}/files/{file_key}",
            tool="get_file_metadata", headers=_headers(self._token), params={"depth": 2},
        )
        document = data.get("document") or {}
        frames: list[dict[str, str]] = []
        for page in document.get("children", []) or []:
            for child in page.get("children", []) or []:
                if child.get("type") in _FRAME_TYPES:
                    frames.append({"id": child.get("id"), "name": child.get("name", "unnamed")})
        return frames


def enumerate_frame_nodes(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Top-level frame nodes (full subtrees) from a file document."""
    out: list[dict[str, Any]] = []
    for page in document.get("children", []) or []:
        for child in page.get("children", []) or []:
            if child.get("type") in _FRAME_TYPES:
                out.append(child)
    return out


def parse_frame_specs(node: dict[str, Any]) -> dict[str, Any]:
    """Pure spec parser (also directly unit-tested for the null-spacing path)."""
    layout_mode = node.get("layoutMode")  # NONE / HORIZONTAL / VERTICAL / None
    spacing: dict[str, Any] = {
        "layout_mode": layout_mode or "NONE",
        "padding": {
            "left": node.get("paddingLeft"),
            "right": node.get("paddingRight"),
            "top": node.get("paddingTop"),
            "bottom": node.get("paddingBottom"),
        },
        "item_spacing": node.get("itemSpacing"),
        "source": "auto_layout",
    }

    has_autolayout = layout_mode in ("HORIZONTAL", "VERTICAL") and spacing["item_spacing"] is not None
    if not has_autolayout:
        # Fallback: compute geometry-based spacing from the bounding box.
        bbox = node.get("absoluteBoundingBox") or {}
        spacing = {
            "layout_mode": layout_mode or "NONE",
            "padding": {"left": 0, "right": 0, "top": 0, "bottom": 0},
            "item_spacing": None,
            "bounding_box": {"width": bbox.get("width"), "height": bbox.get("height")},
            "source": "bounding_box_fallback",
        }

    # Colors from fills (this node + immediate children).
    colors: list[dict[str, Any]] = []
    for fill in _collect_fills(node):
        colors.append(fill)

    # Typography from descendant TEXT nodes.
    typography: list[dict[str, Any]] = []
    for text_node in _iter_text_nodes(node):
        style = text_node.get("style") or {}
        typography.append(
            {
                "text_sample": (text_node.get("characters") or "")[:40],
                "family": style.get("fontFamily"),
                "weight": style.get("fontWeight"),
                "size": style.get("fontSize"),
                "line_height": style.get("lineHeightPx") or style.get("lineHeightPercent"),
            }
        )

    return {
        "node_id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type"),
        "spacing": spacing,
        "colors": colors[:12],
        "typography": typography[:12],
    }


def _collect_fills(node: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def visit(n: dict[str, Any], depth: int) -> None:
        for fill in n.get("fills", []) or []:
            if fill.get("type") == "SOLID" and fill.get("visible", True):
                color = fill.get("color") or {}
                out.append(
                    {
                        "hex": rgba_to_hex(color),
                        "opacity": round(float(color.get("a", 1.0)), 3),
                        "token": n.get("name") if depth == 0 else None,
                    }
                )
        if depth < 2:
            for child in n.get("children", []) or []:
                visit(child, depth + 1)

    visit(node, 0)
    return out


def _iter_text_nodes(node: dict[str, Any]):
    stack = [node]
    while stack:
        n = stack.pop()
        if n.get("type") == "TEXT":
            yield n
        for child in n.get("children", []) or []:
            stack.append(child)


def hash_frame(node: dict[str, Any]) -> str:
    """Stable content hash of a frame subtree for change detection.

    Captures geometry, fills and text so that a genuine edit changes the hash
    while a no-op re-fetch does not.
    """
    def canonical(n: dict[str, Any]) -> Any:
        return {
            "t": n.get("type"),
            "bb": n.get("absoluteBoundingBox"),
            "fills": [f.get("color") for f in (n.get("fills") or []) if f.get("type") == "SOLID"],
            "chars": n.get("characters"),
            "style": {k: (n.get("style") or {}).get(k) for k in ("fontFamily", "fontWeight", "fontSize")},
            "children": [canonical(c) for c in (n.get("children") or [])],
        }

    blob = json.dumps(canonical(node), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
