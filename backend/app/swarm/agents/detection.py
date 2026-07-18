"""Agent 1 — Change Detection.

Decides whether the file changed at all and, if so, hands the changed frames to
Extraction. The no-changes case is a clean success path: it does NOT hand off.
"""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from ...context import RunContext
from ..handoffs import make_handoff_tool

DETECTION_TOOLS = ["get_file_metadata", "get_file_versions", "get_file_nodes", "detect_changes"]


def build_detection_agent(model, tools_by_name: dict, ctx: RunContext):
    tools = [tools_by_name[n] for n in DETECTION_TOOLS if n in tools_by_name]
    handoff = make_handoff_tool(
        from_agent="detection_agent",
        to_agent="extraction_agent",
        ctx=ctx,
        checkpoint_pct=50,  # "Extraction in progress" — fires on the real handoff
        tool_name="handoff_to_extraction",
        description=(
            "Transfer control to the Extraction Agent, passing ONLY the changed frame "
            "names/ids. Requires a plain-language reason and a payload_summary."
        ),
    )
    prompt = (
        "You are the Change Detection Agent in a Figma design-handoff swarm.\n"
        f"The target Figma file_key is: {ctx.state.file_key}\n\n"
        "Your job:\n"
        "1. Call detect_changes with that file_key EXACTLY ONCE. It compares the "
        "current file against the last run's snapshot and returns changed vs "
        "skipped frames plus version markers.\n"
        "2. If it returns no_changes=true (or an empty changed list), the run is a "
        "clean no-op success: reply in one sentence that no changes were detected "
        "and DO NOT hand off to anyone.\n"
        "3. Otherwise, call handoff_to_extraction. In payload_summary list the "
        "changed frame names; in reason explain that those frames need spec "
        "extraction. Pass ONLY changed frames — never the skipped ones.\n"
        "Be concise. Do not invent frames."
    )
    return create_react_agent(model, tools + [handoff], prompt=prompt, name="detection_agent")
