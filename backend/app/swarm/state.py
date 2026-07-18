"""Part 2 — the typed, serializable swarm run state.

`RunState` is the canonical snapshot the frontend consumes (via GET /run/{id}
and the WebSocket). It is a Pydantic model so it serializes cleanly to JSON and
validates on construction. The LangGraph Swarm's internal message state is kept
separate; this model is the durable, inspectable record of a run.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

RunStatus = Literal["idle", "running", "self_healing", "complete", "no_changes"]


class FrameRef(BaseModel):
    id: str
    name: str
    hash: Optional[str] = None


class ColorSpec(BaseModel):
    hex: str
    opacity: float = 1.0
    token: Optional[str] = None


class TypographySpec(BaseModel):
    family: Optional[str] = None
    weight: Optional[float] = None
    size: Optional[float] = None
    line_height: Optional[Any] = None
    text_sample: Optional[str] = None


class FrameSpec(BaseModel):
    node_id: str
    name: str
    type: Optional[str] = None
    spacing: dict[str, Any] = Field(default_factory=dict)
    colors: list[ColorSpec] = Field(default_factory=list)
    typography: list[TypographySpec] = Field(default_factory=list)
    incomplete: bool = False  # set when a spec was degraded/partial after healing


class AssetRef(BaseModel):
    node_id: str
    filename: str
    path: str
    url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

    @property
    def dimensions(self) -> str:
        if self.width and self.height:
            return f"{self.width}×{self.height}"
        return ""


class ErrorRecord(BaseModel):
    tool: str
    error_type: str
    message: str
    at: float = Field(default_factory=time.time)


class HealingEvent(BaseModel):
    tool: str
    attempt: int
    diagnosis: str
    strategy: str
    outcome: Literal["retrying", "recovered", "degraded", "failed"]
    error_type: Optional[str] = None
    at: float = Field(default_factory=time.time)


class RunState(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    run_number: int = 1
    started_at: float = Field(default_factory=time.time)

    file_key: str = ""
    last_known_version: Optional[str] = None
    current_version: Optional[str] = None
    file_name: Optional[str] = None

    changed_frames: list[FrameRef] = Field(default_factory=list)
    skipped_frames: list[FrameRef] = Field(default_factory=list)
    extracted_specs: list[FrameSpec] = Field(default_factory=list)
    exported_assets: list[AssetRef] = Field(default_factory=list)

    summary_payload: Optional[dict[str, Any]] = None
    delivery_result: Optional[dict[str, Any]] = None

    checkpoint: int = 0
    errors: list[ErrorRecord] = Field(default_factory=list)
    healing_events: list[HealingEvent] = Field(default_factory=list)
    learned_patterns_applied: list[str] = Field(default_factory=list)

    status: RunStatus = "idle"

    def snapshot(self) -> dict[str, Any]:
        """JSON-serializable snapshot for the frontend."""
        return self.model_dump(mode="json")
