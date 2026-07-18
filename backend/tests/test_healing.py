"""In-run self-correction + cross-run pattern memory (Part 4)."""
from __future__ import annotations

from app.healing.executor import HealingExecutor, _coerce
from tests.conftest import FakeRaw


def test_coerce_parses_mcp_content_blocks():
    """Successful MCP results arrive as content blocks; must parse to a dict."""
    blocks = [{"type": "text", "text": '{"node_id": "1:2", "name": "Frame 1"}'}]
    out = _coerce(blocks)
    assert isinstance(out, dict) and out["node_id"] == "1:2"
    # plain dict and JSON string forms still work
    assert _coerce({"a": 1}) == {"a": 1}
    assert _coerce('{"b": 2}') == {"b": 2}


async def test_rate_limit_is_healed_and_pattern_learned(ctx, collected_events):
    """429 then success -> recovered, HealingEvent recorded, pattern persisted."""
    raw = FakeRaw(
        "export_asset",
        results=[
            ("raise", "RateLimitError: 429 rate limited [tool=export_asset status=429]"),
            ("ok", {"node_id": "1:2", "filename": "icon@2x.png", "path": "/tmp/icon@2x.png",
                    "url": "https://img", "width": 48, "height": 48}),
        ],
    )
    ex = HealingExecutor(ctx)
    result = await ex._execute(raw, "export_asset", {"file_key": "K", "node_id": "1:2", "scale": 2})

    assert isinstance(result, dict) and result["filename"] == "icon@2x.png"
    outcomes = [h.outcome for h in ctx.state.healing_events]
    assert "retrying" in outcomes and "recovered" in outcomes
    assert ctx.state.exported_assets and ctx.state.exported_assets[0].filename == "icon@2x.png"

    # pattern written back for future runs
    patterns = await ctx.memory.list_patterns()
    assert any(p["tool_name"] == "export_asset" and p["error_signature"].startswith("RateLimitError") for p in patterns)

    types = [e["type"] for e in collected_events]
    assert "error" in types and "healing" in types and "asset_exported" in types


async def test_known_pattern_applied_proactively(ctx, collected_events):
    """A previously-learned pattern fires a pattern_matched event before the call."""
    await ctx.memory.record_pattern(
        run_number=2, tool_name="export_asset",
        error_signature="RateLimitError:export_asset",
        diagnosis="rate limited", resolution_strategy="backoff_reduce_concurrency",
    )
    raw = FakeRaw("export_asset", results=[("ok", {"node_id": "9:9", "filename": "a.png", "path": "/a", "url": "u", "width": 1, "height": 1})])
    ex = HealingExecutor(ctx)
    await ex._execute(raw, "export_asset", {"file_key": "K", "node_id": "9:9", "scale": 2})

    assert any(e["type"] == "pattern_matched" for e in collected_events)
    assert ctx.state.learned_patterns_applied  # appended


async def test_auth_error_degrades_gracefully_not_crash(ctx):
    """Expired/invalid token -> clear degraded result, run continues (no raise)."""
    raw = FakeRaw("get_frame_specs", results=[("raise", "AuthError: authentication failed (401)")])
    ex = HealingExecutor(ctx)
    result = await ex._execute(raw, "get_frame_specs", {"file_key": "K", "node_id": "1:2"})

    assert isinstance(result, str) and result.startswith("TOOL_DEGRADED(get_frame_specs)")
    assert ctx.state.errors and ctx.state.errors[0].error_type == "AuthError"


async def test_retries_are_capped(ctx):
    """A persistent transient error exhausts the cap and degrades, never loops."""
    raw = FakeRaw("get_file_nodes", results=[("raise", "TransientServerError: upstream 503")])
    ex = HealingExecutor(ctx)
    result = await ex._execute(raw, "get_file_nodes", {"file_key": "K", "node_ids": ["1:2"]})
    assert isinstance(result, str) and "TOOL_DEGRADED" in result
    # attempts == max_retries + 1, all recorded
    assert raw.calls == ctx.settings.max_tool_retries + 1
