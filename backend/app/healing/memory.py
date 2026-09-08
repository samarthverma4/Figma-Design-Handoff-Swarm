"""SQLite-backed persistence (aiosqlite).

Three concerns share one database file so both the FastMCP server process (which
computes the change-detection diff) and the main API process (which learns
healing patterns and enforces post idempotency) can reach them:

  learned_patterns   — Part 4B cross-run memory of failure -> resolution
  frame_snapshots    — per-run content hashes powering change detection
  posted_summaries   — idempotency guard so a version is never double-posted

WAL mode is enabled so the two processes can read/write concurrently.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learned_patterns (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_number_learned  INTEGER NOT NULL,
    tool_name           TEXT NOT NULL,
    error_signature     TEXT NOT NULL,
    diagnosis           TEXT NOT NULL,
    resolution_strategy TEXT NOT NULL,
    times_applied       INTEGER NOT NULL DEFAULT 0,
    last_applied_at     TEXT,
    UNIQUE(tool_name, error_signature)
);

CREATE TABLE IF NOT EXISTS frame_snapshots (
    file_key   TEXT NOT NULL,
    version    TEXT NOT NULL,
    node_id    TEXT NOT NULL,
    name       TEXT,
    node_hash  TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (file_key, node_id)
);

CREATE TABLE IF NOT EXISTS posted_summaries (
    file_key   TEXT NOT NULL,
    version    TEXT NOT NULL,
    message_id TEXT,
    permalink  TEXT,
    posted_at  TEXT NOT NULL,
    PRIMARY KEY (file_key, version)
);
"""


class Memory:
    def __init__(self, db: aiosqlite.Connection, path: Path):
        self._db = db
        self.path = path

    @classmethod
    async def open(cls, path: Path | str) -> "Memory":
        path = Path(path)
        db = await aiosqlite.connect(str(path))
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.executescript(_SCHEMA)
        await db.commit()
        return cls(db, path)

    async def close(self) -> None:
        await self._db.close()

    # ---- Learned patterns (Part 4B) ---------------------------------------

    async def find_pattern(self, tool_name: str, error_signature: str) -> dict[str, Any] | None:
        cur = await self._db.execute(
            "SELECT * FROM learned_patterns WHERE tool_name=? AND error_signature=?",
            (tool_name, error_signature),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def record_pattern(
        self,
        *,
        run_number: int,
        tool_name: str,
        error_signature: str,
        diagnosis: str,
        resolution_strategy: str,
    ) -> None:
        """Upsert a learned pattern after a successful in-run heal."""
        now = _now()
        await self._db.execute(
            """
            INSERT INTO learned_patterns
                (run_number_learned, tool_name, error_signature, diagnosis,
                 resolution_strategy, times_applied, last_applied_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(tool_name, error_signature) DO UPDATE SET
                diagnosis=excluded.diagnosis,
                resolution_strategy=excluded.resolution_strategy
            """,
            (run_number, tool_name, error_signature, diagnosis, resolution_strategy, now),
        )
        await self._db.commit()

    async def mark_pattern_applied(self, pattern_id: int) -> None:
        await self._db.execute(
            "UPDATE learned_patterns SET times_applied = times_applied + 1, last_applied_at=? WHERE id=?",
            (_now(), pattern_id),
        )
        await self._db.commit()

    async def list_patterns(self) -> list[dict[str, Any]]:
        cur = await self._db.execute(
            "SELECT * FROM learned_patterns ORDER BY run_number_learned, id"
        )
        return [dict(r) for r in await cur.fetchall()]

    # ---- Frame snapshots (change detection) -------------------------------

    async def get_snapshot(self, file_key: str) -> dict[str, str]:
        cur = await self._db.execute(
            "SELECT node_id, node_hash FROM frame_snapshots WHERE file_key=?", (file_key,)
        )
        return {r["node_id"]: r["node_hash"] for r in await cur.fetchall()}

    async def get_last_version(self, file_key: str) -> str | None:
        cur = await self._db.execute(
            "SELECT version FROM frame_snapshots WHERE file_key=? LIMIT 1", (file_key,)
        )
        row = await cur.fetchone()
        return row["version"] if row else None

    async def save_snapshot(self, file_key: str, version: str, frames: list[dict[str, str]]) -> None:
        now = _now()
        await self._db.execute("DELETE FROM frame_snapshots WHERE file_key=?", (file_key,))
        await self._db.executemany(
            "INSERT INTO frame_snapshots (file_key, version, node_id, name, node_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(file_key, version, f["id"], f.get("name"), f["hash"], now) for f in frames],
        )
        await self._db.commit()

    # ---- Post idempotency -------------------------------------------------

    async def get_post(self, file_key: str, version: str) -> dict[str, Any] | None:
        cur = await self._db.execute(
            "SELECT * FROM posted_summaries WHERE file_key=? AND version=?", (file_key, version)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def record_post(
        self, file_key: str, version: str, message_id: str | None, permalink: str | None
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO posted_summaries (file_key, version, message_id, permalink, posted_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (file_key, version, message_id, permalink, _now()),
        )
        await self._db.commit()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
