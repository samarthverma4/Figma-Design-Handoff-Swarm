"""Spec parsing + change-detection hashing (Part 6: null fields, dedup)."""
from __future__ import annotations

from app.mcp_server.figma_tools import hash_frame, parse_frame_specs, rgba_to_hex


def test_autolayout_specs_parsed():
    node = {
        "id": "1:2", "name": "Buttons", "type": "FRAME",
        "layoutMode": "HORIZONTAL", "itemSpacing": 8,
        "paddingLeft": 16, "paddingRight": 16, "paddingTop": 24, "paddingBottom": 24,
        "fills": [{"type": "SOLID", "visible": True, "color": {"r": 0.48, "g": 0.36, "b": 1.0, "a": 1}}],
        "children": [
            {"type": "TEXT", "characters": "Primary", "style": {"fontFamily": "Inter", "fontWeight": 500, "fontSize": 14}}
        ],
    }
    specs = parse_frame_specs(node)
    assert specs["spacing"]["source"] == "auto_layout"
    assert specs["spacing"]["item_spacing"] == 8
    assert specs["spacing"]["padding"]["left"] == 16
    assert specs["colors"][0]["hex"] == "#7A5CFF"
    assert specs["typography"][0]["family"] == "Inter"


def test_null_spacing_falls_back_to_bounding_box():
    """Edge case: missing/null auto-layout fields -> geometry fallback path."""
    node = {
        "id": "3:4", "name": "Loose Frame", "type": "FRAME",
        "layoutMode": None, "itemSpacing": None,
        "absoluteBoundingBox": {"width": 120, "height": 48},
        "fills": [],
    }
    specs = parse_frame_specs(node)
    assert specs["spacing"]["source"] == "bounding_box_fallback"
    assert specs["spacing"]["bounding_box"] == {"width": 120, "height": 48}


def test_rgba_to_hex():
    assert rgba_to_hex({"r": 1, "g": 1, "b": 1}) == "#FFFFFF"
    assert rgba_to_hex({"r": 0, "g": 0, "b": 0}) == "#000000"


def test_hash_changes_on_edit_and_is_stable():
    base = {"type": "FRAME", "absoluteBoundingBox": {"x": 0, "width": 10}, "children": []}
    edited = {"type": "FRAME", "absoluteBoundingBox": {"x": 0, "width": 20}, "children": []}
    assert hash_frame(base) == hash_frame(dict(base))  # stable
    assert hash_frame(base) != hash_frame(edited)      # detects change
