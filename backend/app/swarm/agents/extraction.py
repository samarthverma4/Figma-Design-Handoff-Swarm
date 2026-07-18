"""Agent 2 — Extraction.

Operates strictly on the changed frames (grounded via get_changed_frames, which
reads the run state populated by detection). Extracts specs, exports at least one
real asset, then hands a structured summary to Posting.
"""
from __future__ import annotations

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from ...context import RunContext
from ..handoffs import make_handoff_tool

EXTRACTION_TOOLS = ["get_frame_specs", "get_published_styles", "export_asset"]


def build_extraction_agent(model, tools_by_name: dict, ctx: RunContext):
    @tool("get_changed_frames", description="Return the changed frames (id + name) this run must extract.")
    async def get_changed_frames() -> list[dict]:
        return [{"id": f.id, "name": f.name} for f in ctx.state.changed_frames]

    tools = [get_changed_frames] + [tools_by_name[n] for n in EXTRACTION_TOOLS if n in tools_by_name]
    handoff = make_handoff_tool(
        from_agent="extraction_agent",
        to_agent="posting_agent",
        ctx=ctx,
        checkpoint_pct=75,  # "Specs extracted · asset exported"
        tool_name="handoff_to_posting",
        description="Transfer the extracted specs + exported asset to the Posting Agent.",
    )
    prompt = (
        "You are the Extraction Agent in a Figma design-handoff swarm.\n"
        f"The target Figma file_key is: {ctx.state.file_key}\n\n"
        "Your job:\n"
        "1. Call get_changed_frames to get the exact list of frames to work on. "
        "Work ONLY on these; never extract any other frame.\n"
        "2. For EACH changed frame, call get_frame_specs(file_key, node_id) to read "
        "its spacing, colors and typography. If the same node appears twice, extract "
        "it only once.\n"
        "3. Call export_asset(file_key, node_id) for at least ONE frame to export a "
        "real image (png, scale 2). \n"
        "4. Optionally call get_published_styles once for library color/text styles.\n"
        "5. When every changed frame has specs and at least one asset is exported, "
        "call handoff_to_posting with a payload_summary of what you extracted and a "
        "reason. Do not post anything yourself.\n"
        "If a tool returns a TOOL_DEGRADED message, note it and continue with the "
        "remaining frames rather than stopping."
    )
    return create_react_agent(model, tools + [handoff], prompt=prompt, name="extraction_agent")
