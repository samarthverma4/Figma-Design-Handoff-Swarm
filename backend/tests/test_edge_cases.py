"""Part 6 edge cases: no-op success, skipped frames, dedup, idempotency, empty."""
from __future__ import annotations

from app.healing.executor import HealingExecutor
from tests.conftest import FakeRaw


async def test_no_changes_is_clean_success_path(ctx, collected_events):
    """File with no recent edits -> status no_changes, checkpoint 10->100, no handoff."""
    ex = HealingExecutor(ctx)
    await ex._after_detect({
        "current_version": "v2", "last_known_version": "v2", "file_name": "DS",
        "changed": [], "skipped": [{"id": "1:1", "name": "A"}], "no_changes": True,
    })
    assert ctx.state.status == "no_changes"
    assert ctx.state.checkpoint == 100
    assert [f.name for f in ctx.state.skipped_frames] == ["A"]


async def test_empty_file_zero_frames_does_not_crash(ctx):
    """File with zero frames -> graceful no_changes, not an error."""
    ex = HealingExecutor(ctx)
    await ex._after_detect({
        "current_version": "v1", "last_known_version": None, "file_name": "Empty",
        "changed": [], "skipped": [], "no_changes": False,
    })
    assert ctx.state.status == "no_changes"
    assert ctx.state.checkpoint == 100


async def test_changed_and_skipped_are_both_recorded(ctx):
    """Unchanged frames are explicitly skipped + kept for auditability."""
    ex = HealingExecutor(ctx)
    await ex._after_detect({
        "current_version": "v3", "last_known_version": "v2", "file_name": "DS",
        "changed": [{"id": "1:1", "name": "Buttons"}],
        "skipped": [{"id": "2:2", "name": "Card"}, {"id": "3:3", "name": "Modal"}],
        "no_changes": False,
    })
    assert [f.name for f in ctx.state.changed_frames] == ["Buttons"]
    assert [f.name for f in ctx.state.skipped_frames] == ["Card", "Modal"]
    assert ctx.state.checkpoint == 30


async def test_duplicate_node_extracted_once(ctx):
    """Dedup: the same node referenced twice is only extracted once."""
    ex = HealingExecutor(ctx)
    spec_result = {"node_id": "1:1", "name": "Buttons", "type": "FRAME",
                   "spacing": {"source": "auto_layout"}, "colors": [], "typography": []}
    await ex._after_specs(spec_result)
    await ex._after_specs(dict(spec_result))  # duplicate
    assert len(ctx.state.extracted_specs) == 1


async def test_duplicate_asset_export_deduped(ctx):
    ex = HealingExecutor(ctx)
    asset = {"node_id": "1:1", "filename": "a.png", "path": "/a", "url": "u", "width": 1, "height": 1}
    await ex._after_export(asset)
    await ex._after_export(dict(asset))
    assert len(ctx.state.exported_assets) == 1


async def test_idempotent_posting_records_once(ctx):
    """Posting the same version twice is guarded by the idempotency store."""
    ctx.state.current_version = "v3"
    await ctx.memory.record_post(ctx.state.file_key, "v3", "170.1", "https://slack/perma")
    existing = await ctx.memory.get_post(ctx.state.file_key, "v3")
    assert existing and existing["message_id"] == "170.1"
    # a second record for the same (file, version) replaces rather than duplicates
    await ctx.memory.record_post(ctx.state.file_key, "v3", "170.2", "https://slack/perma2")
    again = await ctx.memory.get_post(ctx.state.file_key, "v3")
    assert again["message_id"] == "170.2"


async def test_bounding_box_fallback_marks_spec_incomplete(ctx):
    """Malformed/null auto-layout -> spec captured via fallback + flagged incomplete."""
    ex = HealingExecutor(ctx)
    await ex._after_specs({
        "node_id": "5:5", "name": "Loose", "type": "FRAME",
        "spacing": {"source": "bounding_box_fallback"}, "colors": [], "typography": [],
    })
    assert ctx.state.extracted_specs[0].incomplete is True


async def test_change_detection_snapshot_diff(memory):
    """Second run with an unchanged frame is skipped; an edited one is flagged."""
    await memory.save_snapshot("K", "v1", [
        {"id": "1:1", "name": "Buttons", "hash": "aaa"},
        {"id": "2:2", "name": "Card", "hash": "bbb"},
    ])
    prior = await memory.get_snapshot("K")
    # simulate a new run: Buttons edited (new hash), Card unchanged
    new = {"1:1": "ZZZ", "2:2": "bbb"}
    changed = [nid for nid, h in new.items() if prior.get(nid) != h]
    skipped = [nid for nid, h in new.items() if prior.get(nid) == h]
    assert changed == ["1:1"] and skipped == ["2:2"]
