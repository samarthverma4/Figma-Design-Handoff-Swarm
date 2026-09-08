"""Agent 3 — Posting.

Formats the extracted specs + asset into a developer-readable summary and posts
it to Slack via the real post_summary MCP tool. Idempotent: a summary for an
already-posted version is never sent twice.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from ...context import RunContext
from ...mcp_server.slack_tools import build_slack_payload
from ...stream import checkpoints, events


def _summary_from_state(ctx: RunContext) -> dict[str, Any]:
    s = ctx.state
    return {
        "file_name": s.file_name or "Figma file",
        "current_version": s.current_version or "?",
        "changed_frames": [f.name for f in s.changed_frames],
        "skipped_frames": [f.name for f in s.skipped_frames],
        "specs": [spec.model_dump(mode="json") for spec in s.extracted_specs],
        "asset": (
            {
                "filename": s.exported_assets[0].filename,
                "dimensions": s.exported_assets[0].dimensions,
                "url": s.exported_assets[0].url,
            }
            if s.exported_assets else None
        ),
    }


def build_posting_agent(model, tools_by_name: dict, ctx: RunContext):
    wrapped_post = tools_by_name["post_summary"]
    destination = ctx.settings.delivery_destination

    @tool("deliver", description="Format and post the dev-ready summary to Slack. Idempotent per version.")
    async def deliver() -> dict:
        version = ctx.state.current_version
        # Idempotency: never double-post the same version.
        existing = await ctx.memory.get_post(ctx.state.file_key, version) if version else None
        if existing:
            await ctx.emit(events.delivery(ctx.run_id, destination, existing.get("permalink"), "skipped_idempotent"))
            await ctx.checkpoint(100, checkpoints.label_for(100))
            ctx.state.delivery_result = {"ok": True, "idempotent": True, **existing}
            return {"status": "already_posted_this_version", **existing}

        payload = build_slack_payload(_summary_from_state(ctx))
        ctx.state.summary_payload = payload
        # Real MCP post_summary, routed through the healing executor (which emits
        # the delivery event + final checkpoint + records idempotency on success).
        result = await wrapped_post.ainvoke({"destination": destination, "payload": payload})
        return result if isinstance(result, dict) else {"result": result}

    prompt = (
        "You are the Posting Agent in a Figma design-handoff swarm.\n"
        "Call deliver() EXACTLY ONCE to post the developer-ready summary to Slack, "
        "then reply with the returned message link as proof. Do not call deliver "
        "more than once. You have no other tools."
    )
    return create_react_agent(model, [deliver], prompt=prompt, name="posting_agent")
