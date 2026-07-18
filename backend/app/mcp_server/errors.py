"""Normalized, distinguishable error types for Figma/Slack operations.

The self-healing layer selects a corrective strategy based on the *type* of
failure, so every network/HTTP failure is mapped to exactly one of these.

Because tools are invoked across the MCP boundary (where a raised Python
exception is serialized to a string), each error carries a stable, machine
readable ``signature`` of the form ``"<ErrorClass>:<tool>:<detail>"``. The
healing executor parses the leading class name back out to re-classify.
"""
from __future__ import annotations


class FigmaAPIError(Exception):
    """Base class for all normalized upstream errors."""

    #: short, stable code used in the error signature
    code: str = "FigmaAPIError"

    def __init__(self, message: str, *, tool: str = "", status: int | None = None):
        self.tool = tool
        self.status = status
        self.detail = message
        super().__init__(message)

    @property
    def signature(self) -> str:
        return f"{self.code}:{self.tool}:{self.status or ''}"

    def as_tool_error(self) -> str:
        """String surfaced through MCP; must start with the class name so the
        healing executor can re-classify it on the far side of the boundary."""
        return f"{self.code}: {self.detail} [tool={self.tool} status={self.status}]"


class RateLimitError(FigmaAPIError):
    code = "RateLimitError"


class NotFoundError(FigmaAPIError):
    code = "NotFoundError"


class AuthError(FigmaAPIError):
    code = "AuthError"


class MalformedResponseError(FigmaAPIError):
    code = "MalformedResponseError"


class TransientServerError(FigmaAPIError):
    """5xx that is worth a bounded retry with jitter."""

    code = "TransientServerError"


# Ordered registry for re-classifying an error string coming back over MCP.
_ERROR_CLASSES = [
    RateLimitError,
    NotFoundError,
    AuthError,
    MalformedResponseError,
    TransientServerError,
    FigmaAPIError,
]


def classify_error_string(text: str) -> str:
    """Given an arbitrary tool-error string, return the canonical error code.

    Used by the healing executor: MCP flattens exceptions to text, so we sniff
    the leading class name. Falls back to ``FigmaAPIError`` for anything unknown.
    """
    head = (text or "").strip()
    for cls in _ERROR_CLASSES:
        if head.startswith(cls.code):
            return cls.code
    # Heuristic fallbacks for errors that didn't originate from us.
    lowered = head.lower()
    if "429" in head or "rate" in lowered:
        return RateLimitError.code
    if "not found" in lowered or "404" in head:
        return NotFoundError.code
    if "401" in head or "403" in head or "unauthor" in lowered or "token" in lowered:
        return AuthError.code
    if any(code in head for code in ("500", "502", "503", "504")):
        return TransientServerError.code
    return FigmaAPIError.code
