"""Shared async HTTP client for Figma + Slack.

Responsibilities:
  * request timeout
  * exponential backoff on 429 / 5xx (bounded)
  * map HTTP status -> normalized typed errors (errors.py)
  * NEVER log token values (Authorization header is redacted in all logs)
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from .errors import (
    AuthError,
    FigmaAPIError,
    MalformedResponseError,
    NotFoundError,
    RateLimitError,
    TransientServerError,
)

log = logging.getLogger("swarm.http")

_RETRYABLE = {429, 500, 502, 503, 504}


class HttpClient:
    """Thin wrapper over httpx.AsyncClient with typed errors + backoff.

    The healing executor performs the *strategic* retries (reduce concurrency,
    alternate extraction path, re-resolve node id, ...). This client performs
    only the low-level transport-safety retries so a single blip doesn't bubble
    up as a hard failure. Both layers respect a retry cap.
    """

    def __init__(self, *, timeout: float = 30.0, max_transport_retries: int = 1, max_backoff: float = 3.0):
        self._timeout = timeout
        self._max_transport_retries = max_transport_retries
        self._max_backoff = max_backoff
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HttpClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        tool: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> dict[str, Any]:
        resp = await self._send(method, url, tool=tool, headers=headers, params=params, json_body=json_body)
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise MalformedResponseError(
                f"non-JSON response from {url}: {exc}", tool=tool, status=resp.status_code
            ) from exc
        if not isinstance(data, dict):
            raise MalformedResponseError(
                f"expected JSON object from {url}, got {type(data).__name__}",
                tool=tool,
                status=resp.status_code,
            )
        return data

    async def request_bytes(
        self,
        method: str,
        url: str,
        *,
        tool: str,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        resp = await self._send(method, url, tool=tool, headers=headers)
        return resp.content

    async def _send(
        self,
        method: str,
        url: str,
        *,
        tool: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self.client.request(
                    method, url, headers=headers, params=params, json=json_body
                )
            except httpx.TimeoutException as exc:
                if attempt <= self._max_transport_retries:
                    await self._sleep_backoff(attempt)
                    continue
                raise TransientServerError(f"timeout after {attempt} attempts: {exc}", tool=tool) from exc
            except httpx.HTTPError as exc:
                raise TransientServerError(f"transport error: {exc}", tool=tool) from exc

            # Redacted logging — never include Authorization header or token.
            log.debug("HTTP %s %s -> %s (attempt %d)", method, _safe_url(url), resp.status_code, attempt)

            if resp.status_code in _RETRYABLE and attempt <= self._max_transport_retries:
                await self._sleep_backoff(attempt, retry_after=resp.headers.get("Retry-After"))
                continue

            self._raise_for_status(resp, tool=tool)
            return resp

    async def _sleep_backoff(self, attempt: int, retry_after: str | None = None) -> None:
        # Honor Retry-After but cap it so the live console reads naturally instead
        # of stalling on a large upstream value.
        if retry_after:
            try:
                await asyncio.sleep(min(float(retry_after), self._max_backoff))
                return
            except ValueError:
                pass
        # exponential backoff with jitter, capped at max_backoff
        base = min(0.5 * (2 ** (attempt - 1)), self._max_backoff)
        await asyncio.sleep(base + random.uniform(0, 0.3))

    @staticmethod
    def _raise_for_status(resp: httpx.Response, *, tool: str) -> None:
        code = resp.status_code
        if code < 400:
            return
        detail = _short_body(resp)
        if code == 429:
            raise RateLimitError(f"rate limited: {detail}", tool=tool, status=code)
        if code in (401, 403):
            raise AuthError(
                f"authentication failed ({code}). Check that the token is valid and not expired: {detail}",
                tool=tool,
                status=code,
            )
        if code == 404:
            raise NotFoundError(f"resource not found: {detail}", tool=tool, status=code)
        if code >= 500:
            raise TransientServerError(f"upstream {code}: {detail}", tool=tool, status=code)
        if code == 400 and "file type not supported" in detail.lower():
            raise NotFoundError(
                "This file key points to a Figma Slides or FigJam file, which the "
                "REST API does not support. Provide a Design file key "
                "(from a figma.com/design/<KEY>/ or /file/<KEY>/ URL).",
                tool=tool,
                status=code,
            )
        raise FigmaAPIError(f"unexpected {code}: {detail}", tool=tool, status=code)


def _short_body(resp: httpx.Response) -> str:
    try:
        text = resp.text
    except Exception:  # noqa: BLE001
        return "<unreadable body>"
    return (text or "").strip()[:280]


def _safe_url(url: str) -> str:
    """Strip query strings that might carry sensitive identifiers from logs."""
    return url.split("?", 1)[0]
