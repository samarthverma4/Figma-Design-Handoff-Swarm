"""Progress checkpoints (Part 5).

Checkpoints fire at genuine milestones (real tool completions / handoffs /
delivery) — never on a timer. The labels below are the canonical sequence; the
N-frames count is filled in at emit time.
"""
from __future__ import annotations

CHECKPOINTS = {
    10: "Change detection started",
    30: "Change detection complete · {n} frames changed",
    50: "Extraction in progress",
    75: "Specs extracted · asset exported",
    90: "Posting to {destination}",
    100: "Summary posted · run complete",
}

NO_CHANGES_LABEL = "No changes detected · no handoff required"


def label_for(pct: int, **fmt) -> str:
    raw = CHECKPOINTS.get(pct, "")
    try:
        return raw.format(**fmt)
    except (KeyError, IndexError):
        return raw
