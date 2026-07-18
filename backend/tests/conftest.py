"""Shared fixtures + fakes so tests never touch live Figma/Slack/LLM."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.context import RunContext
from app.healing.memory import Memory
from app.stream.websocket import EventBus
from app.swarm.state import RunState


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        figma_token="figd_test",
        figma_file_key="TESTKEY",
        slack_bot_token="xoxb-test",
        slack_channel_id="C_TEST",
        azure_api_key="azkey",
        azure_endpoint="https://example.openai.azure.com",
        azure_deployment="gpt-4.1-nano",
        azure_api_version="2024-12-01-preview",
        delivery_destination="slack",
        http_timeout_seconds=5.0,
        max_tool_retries=3,
        asset_dir=tmp_path / "exports",
        sqlite_path=tmp_path / "mem.db",
    )


@pytest.fixture
async def memory(settings: Settings) -> Memory:
    mem = await Memory.open(settings.sqlite_path)
    yield mem
    await mem.close()


@pytest.fixture
def collected_events() -> list[dict]:
    return []


@pytest.fixture
async def ctx(settings: Settings, memory: Memory, collected_events: list[dict]) -> RunContext:
    bus = EventBus()

    async def _capture(event):
        collected_events.append(event)

    # Wrap the bus publish so tests can assert on emitted events.
    orig = bus.publish

    async def publish(event):
        collected_events.append(event)
        await orig(event)

    bus.publish = publish  # type: ignore[assignment]

    state = RunState(run_number=3, file_key=settings.figma_file_key)
    return RunContext(state=state, bus=bus, memory=memory, settings=settings)


class FakeRaw:
    """Stands in for a raw MCP StructuredTool. Scripted per-call behaviour."""

    def __init__(self, name: str, results: list):
        self.name = name
        self.description = f"fake {name}"
        self.args_schema = None
        self._results = results
        self.calls = 0

    async def ainvoke(self, kwargs):
        idx = min(self.calls, len(self._results) - 1)
        kind, value = self._results[idx]
        self.calls += 1
        if kind == "raise":
            raise Exception(value)
        return value
