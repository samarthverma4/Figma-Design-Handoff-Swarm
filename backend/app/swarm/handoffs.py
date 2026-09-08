"""Explicit handoff tools for the LangGraph Swarm.

These are peer-to-peer handoffs (not a supervisor chain). Each handoff tool
forces the LLM to state, in plain language, WHY it is handing off and WHAT
scoped context it is passing — both are logged and streamed as a `handoff`
event, and the milestone checkpoint fires here (a genuine transition, not a
timer).
"""
from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from ..context import RunContext
from ..stream import checkpoints, events


def make_handoff_tool(
    *,
    from_agent: str,
    to_agent: str,
    ctx: RunContext,
    checkpoint_pct: int | None,
    tool_name: str,
    description: str,
):
    @tool(tool_name, description=description)
    async def _handoff(
        reason: Annotated[str, "Plain-language reason this handoff is necessary."],
        payload_summary: Annotated[str, "The scoped context handed to the next agent."],
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        await ctx.emit(
            events.handoff(ctx.run_id, from_agent, to_agent, payload_summary, reason)
        )
        if checkpoint_pct is not None:
            await ctx.checkpoint(
                checkpoint_pct,
                checkpoints.label_for(checkpoint_pct, destination=ctx.settings.delivery_destination),
            )
        await ctx.agent_status(from_agent, "handoff", None)

        tool_msg = ToolMessage(
            content=f"Handed off to {to_agent}. Context: {payload_summary}",
            name=tool_name,
            tool_call_id=tool_call_id,
        )
        # Pass the FULL message history + this tool response (matching
        # langgraph-swarm's create_handoff_tool). Passing only [tool_msg] leaves
        # the parent graph with a dangling 'tool' message and Azure rejects it
        # ("tool message must follow a message with tool_calls").
        messages = state["messages"] if isinstance(state, dict) else getattr(state, "messages")
        return Command(
            goto=to_agent,
            graph=Command.PARENT,
            update={"messages": [*messages, tool_msg], "active_agent": to_agent},
        )

    return _handoff
