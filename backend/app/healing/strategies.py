"""Corrective strategies keyed by normalized error type (Part 4A).

A strategy is pure metadata + an async ``prepare`` hook that adjusts how the
next retry runs (e.g. backoff, reduced scale, alternate arguments). The executor
owns the retry loop; strategies decide *how* each retry differs.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..mcp_server.errors import (
    AuthError,
    MalformedResponseError,
    NotFoundError,
    RateLimitError,
    TransientServerError,
)


@dataclass
class Strategy:
    name: str
    diagnosis: str
    # mutate the kwargs for the next attempt (return possibly-new kwargs)
    prepare: Callable[[int, dict[str, Any]], "asyncio.Future | Any"]
    recoverable: bool = True


async def _backoff_reduce_concurrency(attempt: int, kwargs: dict[str, Any]) -> dict[str, Any]:
    # exponential backoff (capped for demo snappiness), then batch/reduce load.
    await asyncio.sleep(min(0.5 * (2 ** attempt), 2.5) + random.uniform(0, 0.3))
    if "scale" in kwargs and isinstance(kwargs["scale"], (int, float)) and kwargs["scale"] > 1:
        kwargs = {**kwargs, "scale": max(1, kwargs["scale"] / 2)}
    return kwargs


async def _alternate_extraction(attempt: int, kwargs: dict[str, Any]) -> dict[str, Any]:
    # The alternate path is handled inside get_frame_specs (bounding-box
    # fallback); here we simply signal a straight retry with a short pause.
    await asyncio.sleep(0.2)
    return kwargs


async def _reresolve_then_retry(attempt: int, kwargs: dict[str, Any]) -> dict[str, Any]:
    # A fresh file fetch happens implicitly on the retried call; pause briefly.
    await asyncio.sleep(0.3)
    return kwargs


async def _bounded_jitter(attempt: int, kwargs: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(min(0.4 * (2 ** attempt), 2.5) + random.uniform(0, 0.4))
    return kwargs


async def _no_retry(attempt: int, kwargs: dict[str, Any]) -> dict[str, Any]:
    return kwargs


_STRATEGIES: dict[str, Strategy] = {
    RateLimitError.code: Strategy(
        name="backoff_reduce_concurrency",
        diagnosis="rate limited (429) — back off exponentially, then batch/reduce request size",
        prepare=_backoff_reduce_concurrency,
    ),
    MalformedResponseError.code: Strategy(
        name="alternate_extraction_path",
        diagnosis="malformed/null field — fall back to bounding-box geometry extraction",
        prepare=_alternate_extraction,
    ),
    NotFoundError.code: Strategy(
        name="reresolve_node_and_retry",
        diagnosis="node not found — re-resolve id from a fresh file fetch, retry once",
        prepare=_reresolve_then_retry,
    ),
    TransientServerError.code: Strategy(
        name="bounded_retry_with_jitter",
        diagnosis="transient 5xx — bounded retry with jitter",
        prepare=_bounded_jitter,
    ),
    AuthError.code: Strategy(
        name="fail_fast_auth",
        diagnosis="authentication failed — token invalid/expired, not retryable",
        prepare=_no_retry,
        recoverable=False,
    ),
}


def strategy_for(error_code: str) -> Optional[Strategy]:
    return _STRATEGIES.get(error_code)
