# Figma Design Handoff Swarm — Backend

A multi-agent system that detects changes in a Figma file, extracts design specs
and assets, and posts a developer-ready summary to Slack — while streaming a live
event feed to the monitoring dashboard.

Built with **LangChain + LangGraph Swarm**, **MCP (FastMCP)** for all Figma/Slack
operations, **FastAPI + WebSocket** for the event stream, and **SQLite** for
cross-run "learned pattern" memory.

---

## Architecture

```
POST /run ─▶ RunContext(RunState + EventBus + Memory)
                │
                ▼
        LangGraph Swarm  (peer agents, explicit handoffs)
     ┌───────────────┬────────────────┬──────────────┐
     │ detection_agent│ extraction_agent│ posting_agent│
     └───────┬───────┴────────┬───────┴──────┬───────┘
             │  every tool call routed through │
             ▼                                 ▼
     HealingExecutor ──▶ real MCP tools ──▶ FastMCP server (stdio subprocess)
             │                                 │
     emits typed events               real Figma REST + Slack API
             │                                 │
             ▼                                 ▼
        EventBus ──▶ WS /ws/run          SQLite (patterns, snapshots, idempotency)
```

- **All Figma + Slack access is real MCP.** `app/mcp_server/server.py` is a
  FastMCP server exposing 8 tools; the swarm loads them over a stdio session via
  `langchain-mcp-adapters`, so the agents call genuine MCP tools.
- **One instrumentation seam.** Every tool call goes through `HealingExecutor`,
  which emits the `cursor_action` *before* the real call (so the ghost cursor
  tracks genuine work), runs the capped retry/heal loop, and mutates `RunState`
  from the structured result.
- **Checkpoints fire on real milestones** (tool completions / handoffs /
  delivery), never on timers.

### Project layout
```
app/
  mcp_server/  errors.py http_client.py figma_tools.py slack_tools.py server.py
  swarm/       state.py handoffs.py graph.py  agents/{detection,extraction,posting}.py
  healing/     executor.py strategies.py memory.py
  stream/      events.py checkpoints.py websocket.py
  config.py  context.py  llm.py  main.py
tests/         one test per Part-6 edge case + healing-path tests
```

---

## Setup

Requires **Python 3.11+** (developed on 3.12).

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in the values below
```

### Environment (`.env`)

| Var | Required | Notes |
|-----|----------|-------|
| `FIGMA_TOKEN` | ✅ | Personal access token. Needs `file_content:read`, `file_metadata:read`, `file_versions:read`, `library_content:read`. |
| `FIGMA_FILE_KEY` | ✅ | **Must be a Design file** (`figma.com/design/<KEY>/…`). Slides/FigJam are not supported by Figma's REST API. |
| `SLACK_BOT_TOKEN` | ✅ | `xoxb-…` with `chat:write`. Invite the bot to the channel. |
| `SLACK_CHANNEL_ID` | ✅ | e.g. `C0123ABC456`. |
| `AZURE_OPENAI_API_KEY` | ✅ | Data-plane key for the Azure OpenAI resource. |
| `AZURE_OPENAI_ENDPOINT` | ✅ | e.g. `https://<resource>.openai.azure.com`. |
| `AZURE_OPENAI_DEPLOYMENT` | | Deployment **name** (not model id). Default `gpt-4o`. |
| `AZURE_OPENAI_API_VERSION` | | Default `2024-10-21`. |

Missing required keys fail fast at startup with a clear message. Secrets are
never logged (only presence + length).

---

## Run

```bash
python -m app.main        # serves on http://0.0.0.0:8000
```

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/run` | Start a genuine end-to-end swarm run. Body: `{ "file_key": "..." }` (optional; defaults to `FIGMA_FILE_KEY`). |
| `GET` | `/run/{id}` | Serialized `RunState` snapshot. |
| `GET` | `/patterns` | Learned healing patterns (cross-run memory). |
| `GET` | `/health` | Liveness + redacted config. |
| `WS` | `/ws/run` | Live typed event stream (optional `?run_id=`). |

```bash
curl -XPOST localhost:8000/run -H 'content-type: application/json' -d '{}'
# then watch events on ws://localhost:8000/ws/run
```

The dashboard (Vite app at repo root, port 8080) consumes `/ws/run`.

---

## The three agents (LangGraph Swarm)

Peer agents with **explicit handoff tools** — each handoff forces the LLM to
state, in plain language, *why* it's handing off and *what* scoped context it
passes (both logged + streamed as a `handoff` event).

1. **Change Detection** — `get_file_metadata`, `get_file_versions`,
   `get_file_nodes`, `detect_changes`. Diffs each frame's content hash against
   the previous run's SQLite snapshot. **No changes ⇒ clean success path**: sets
   `status=no_changes`, jumps checkpoint 10→100, and does **not** hand off.
2. **Extraction** — `get_frame_specs`, `get_published_styles`, `export_asset`.
   Works *only* on changed frames (grounded via `get_changed_frames`), extracts
   spacing/color/typography, exports a real asset to `exports/`, dedupes repeated
   nodes, then hands off.
3. **Posting** — formats a dev-readable summary and posts to Slack via the real
   `post_summary` MCP tool. Idempotent: a version already posted is never
   double-posted.

> Note: `detect_changes` and the extraction/posting helper tools (`get_changed_frames`,
> `deliver`) are thin, deterministic wrappers built on the required primitives.
> They exist because an LLM cannot reliably diff raw node trees or shuttle large
> payloads verbatim — the real Figma/Slack work still happens through MCP tools
> and is fully instrumented/healed.

---

## Self-healing

**A) In-run correction** (`healing/executor.py` + `strategies.py`). Every tool
call is capped at `MAX_TOOL_RETRIES` (default 3). On a typed failure a strategy
is chosen by error type:

| Error | Strategy |
|-------|----------|
| `RateLimitError` | exponential backoff, then reduce concurrency / batch |
| `MalformedResponseError` | alternate path — bounding-box geometry fallback |
| `NotFoundError` | re-resolve node id from a fresh fetch, retry once |
| `TransientServerError` (5xx) | bounded retry with jitter |
| `AuthError` | fail fast (not retryable) |

Every attempt, diagnosis, strategy and outcome is recorded as a `HealingEvent`
and streamed. If a strategy exhausts, the run **degrades gracefully** — records
the failure, marks the item incomplete, and continues with partial results
instead of aborting the swarm.

**B) Cross-run memory** (`healing/memory.py`). Successful heals are written to
`learned_patterns (tool_name, error_signature, diagnosis, resolution_strategy,
times_applied, …)`. Before a call, the executor checks this store; a known
pattern is applied proactively (emits `pattern_matched`, appends to
`learned_patterns_applied`). Exposed at `GET /patterns`.

---

## Event stream (Part 5)

Typed JSON on `/ws/run`: `run_started`, `checkpoint`, `agent_status`, `handoff`,
`cursor_action`, `spec_extracted`, `asset_exported`, `error`, `healing`,
`pattern_matched`, `delivery`, `run_complete`.

Checkpoint sequence (genuine milestones): **10** detection started · **30**
detection complete (N changed) · **50** extraction in progress · **75** specs +
asset · **90** posting · **100** complete. No-changes path: **10 → 100**.

---

## Edge cases (all handled + tested)

`tests/` has one test per required edge case plus healing-path tests
(`pytest -q`, 22 tests, no live calls):

- File with no edits → clean no-op success
- Unchanged frames → explicitly skipped, never re-extracted
- Failed API call → self-healed and retried
- Null/missing Figma fields → bounding-box fallback (spec flagged incomplete)
- Duplicate nodes → deduped; duplicate posts → idempotent
- Empty file (zero frames) → graceful no-op, no crash
- Expired/invalid token → clear `AuthError`, graceful degrade

---

## Verified live

`POST /run` against a real Figma file drives the real MCP subprocess, real Figma
REST calls, and the Azure-OpenAI-powered swarm, streaming the full event feed.
Because the demo file provided was a **Slides** file (unsupported by Figma's REST
API), the live run exercises the real self-healing + graceful-degradation path
(including a genuine Figma 429 mid-retry). Point `FIGMA_FILE_KEY` at a **Design**
file to see the full extraction → Slack delivery happy path.
