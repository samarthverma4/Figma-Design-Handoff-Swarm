"""Normalized, distinguishable error types (Part 6: expired/invalid token)."""
from __future__ import annotations

import httpx
import pytest

from app.mcp_server.errors import (
    AuthError,
    NotFoundError,
    RateLimitError,
    TransientServerError,
    classify_error_string,
)
from app.mcp_server.http_client import HttpClient


def _resp(status: int, body: str = "") -> httpx.Response:
    return httpx.Response(status_code=status, text=body, request=httpx.Request("GET", "https://x"))


def test_401_maps_to_autherror():
    with pytest.raises(AuthError):
        HttpClient._raise_for_status(_resp(401, "invalid token"), tool="t")


def test_429_maps_to_ratelimit():
    with pytest.raises(RateLimitError):
        HttpClient._raise_for_status(_resp(429), tool="t")


def test_404_maps_to_notfound():
    with pytest.raises(NotFoundError):
        HttpClient._raise_for_status(_resp(404), tool="t")


def test_500_maps_to_transient():
    with pytest.raises(TransientServerError):
        HttpClient._raise_for_status(_resp(503), tool="t")


def test_slides_file_400_is_actionable_notfound():
    with pytest.raises(NotFoundError) as ei:
        HttpClient._raise_for_status(_resp(400, '{"err":"File type not supported by this endpoint"}'), tool="t")
    assert "Design file key" in str(ei.value)


def test_classify_error_string_roundtrips_across_mcp_boundary():
    # errors are flattened to strings across MCP; classification must recover them
    assert classify_error_string("RateLimitError: rate limited [status=429]") == "RateLimitError"
    assert classify_error_string("AuthError: authentication failed") == "AuthError"
    assert classify_error_string("NotFoundError: missing") == "NotFoundError"
    assert classify_error_string("weird 429 thing") == "RateLimitError"
