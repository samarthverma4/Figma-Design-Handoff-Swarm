import type { AgentId, RunState, LogSeverity, Spec } from "./types";
import { createInitialState } from "./initial-state";

/**
 * Pure translation layer: backend WebSocket events -> frontend RunState.
 *
 * Kept free of React so it can be unit-tested in isolation. The live hook
 * (use-live-run-engine.ts) is a thin wrapper that pipes ws.onmessage frames
 * through applyEvent.
 */

// RunState carries a hidden wall-clock anchor so log timestamps read run-relative.
declare module "./types" {
  interface RunState {
    __startedAt?: number;
  }
}

export interface WsEvent {
  type: string;
  run_id?: string;
  timestamp?: number;
  [k: string]: unknown;
}

// backend agent id -> frontend agent id
export const AGENT_MAP: Record<string, AgentId> = {
  detection_agent: "detect",
  extraction_agent: "extract",
  posting_agent: "post",
};

let logCounter = 1;

function pushLog(state: RunState, severity: LogSeverity, text: string, agent?: AgentId, ts?: number): RunState {
  const t = state.__startedAt != null && ts != null ? ts * 1000 - state.__startedAt : state.logs.at(-1)?.t ?? 0;
  return {
    ...state,
    logs: [...state.logs, { id: logCounter++, t, severity, text, agent }].slice(-120),
  };
}

function markCheckpoint(state: RunState, pct: number, label?: string): RunState {
  const idx = state.checkpoints.findIndex((c) => c.pct === pct);
  return {
    ...state,
    checkpoints: state.checkpoints.map((c, i) => {
      if (c.pct === pct) return { ...c, done: true, active: true, label: label ?? c.label };
      if (i < idx) return { ...c, active: false, done: true };
      return { ...c, active: false };
    }),
  };
}

function setAgent(state: RunState, id: AgentId, patch: Partial<RunState["agents"]["detect"]>): RunState {
  return { ...state, agents: { ...state.agents, [id]: { ...state.agents[id], ...patch } } };
}

function dimensions(dim: string): { w?: number; h?: number } {
  const m = /(\d+)\s*[×x]\s*(\d+)/.exec(dim || "");
  return m ? { w: Number(m[1]), h: Number(m[2]) } : {};
}

export function applyEvent(state: RunState, e: WsEvent): RunState {
  switch (e.type) {
    case "run_started": {
      const base = createInitialState(Number(e.run_number ?? state.runNumber));
      base.runStatus = "RUNNING";
      base.running = true;
      base.__startedAt = (e.timestamp ?? Date.now() / 1000) * 1000;
      return pushLog(base, "system", `run #${e.run_number} started · ${String(e.file_key ?? "")}`, undefined, e.timestamp);
    }

    case "checkpoint": {
      const pct = Number(e.pct);
      let s = markCheckpoint(state, pct, String(e.label ?? ""));
      if (pct === 90) s = { ...s, delivery: { ...s.delivery, typing: true, linesShown: 0, delivered: false } };
      if (pct === 100) s = { ...s, runStatus: "COMPLETE" };
      return pushLog(s, "info", `checkpoint ${pct}% · ${String(e.label ?? "")}`, undefined, e.timestamp);
    }

    case "agent_status": {
      const id = AGENT_MAP[String(e.agent)];
      if (!id) return state;
      const status = String(e.status);
      const feStatus: RunState["agents"]["detect"]["status"] =
        status === "active" ? "active"
        : status === "error" ? "error"
        : status === "handoff" ? "handoff"
        : status === "done" ? "done"
        : "active";
      return setAgent(state, id, {
        status: feStatus,
        tool: e.current_tool ? String(e.current_tool) : state.agents[id].tool,
      });
    }

    case "handoff": {
      const from = AGENT_MAP[String(e.from_agent)];
      const to = AGENT_MAP[String(e.to_agent)];
      if (!from || !to) return state;
      const s = {
        ...state,
        handoff: { from, to, payload: String(e.payload_summary ?? ""), active: true, key: Date.now() },
      };
      return pushLog(s, "system", `handoff ${from}→${to} · ${String(e.reason ?? "")}`, undefined, e.timestamp);
    }

    case "cursor_action": {
      const x = typeof e.x === "number" ? e.x : state.cursor.x;
      const y = typeof e.y === "number" ? e.y : state.cursor.y;
      const action = String(e.action ?? "");
      let s: RunState = { ...state, cursor: { x, y, caption: String(e.caption ?? "") } };
      if (action === "export" || action === "post") s = { ...s, clickPulseKey: s.clickPulseKey + 1 };
      if (action === "export") s = { ...s, toast: "exporting asset…" };
      return s;
    }

    case "spec_extracted": {
      const spec = (e.spec ?? {}) as {
        spacing?: { item_spacing?: number | null };
        colors?: Array<{ hex: string; token?: string | null }>;
        typography?: Array<{ family?: string; weight?: number; size?: number }>;
      };
      const additions: Spec[] = [];
      const gap = spec.spacing?.item_spacing;
      if (typeof gap === "number") additions.push({ kind: "spacing", token: "gap", px: gap });
      for (const c of (spec.colors ?? []).slice(0, 2)) {
        additions.push({ kind: "color", token: c.token || "fill", hex: c.hex });
      }
      for (const t of (spec.typography ?? []).slice(0, 1)) {
        additions.push({ kind: "type", token: "text", family: t.family || "Inter", weight: t.weight || 400, size: t.size || 14 });
      }
      const nextFrameIdx = state.frames.findIndex((f) => !f.highlighted && !f.skipped);
      const frames = nextFrameIdx >= 0
        ? state.frames.map((f, i) => (i === nextFrameIdx ? { ...f, highlighted: true } : f))
        : state.frames;
      const s = { ...state, specs: [...state.specs, ...additions], frames };
      return pushLog(s, "info", `spec extracted · ${String(e.frame ?? "")}`, "extract", e.timestamp);
    }

    case "asset_exported": {
      const { w, h } = dimensions(String(e.dimensions ?? ""));
      const s: RunState = {
        ...state,
        toast: null,
        asset: { filename: String(e.filename ?? "asset.png"), width: w ?? 48, height: h ?? 48, ready: true },
      };
      return pushLog(s, "success", `asset exported · ${String(e.filename ?? "")} ${String(e.dimensions ?? "")}`, "extract", e.timestamp);
    }

    case "error":
      return pushLog(state, "error", `${String(e.tool)} → ${String(e.error_type)}: ${String(e.message ?? "").slice(0, 100)}`, undefined, e.timestamp);

    case "healing": {
      const outcome = String(e.outcome ?? "");
      const sev: LogSeverity =
        outcome === "recovered" ? "success"
        : outcome === "retrying" ? "warn"
        : outcome === "degraded" || outcome === "failed" ? "error"
        : "info";
      let s = { ...state };
      if (outcome === "retrying") s = { ...s, runStatus: "SELF-HEALING" };
      if (outcome === "recovered") s = { ...s, runStatus: "RUNNING" };
      return pushLog(s, sev, `healing[${outcome}] ${String(e.strategy ?? "")} · ${String(e.tool ?? "")}`, undefined, e.timestamp);
    }

    case "pattern_matched": {
      const s = {
        ...state,
        learned: state.learned.map((l, i) => (i === 0 ? { ...l, matchedNow: true } : l)),
      };
      return pushLog(s, "system", `pattern matched → applying known fix: ${String(e.resolution ?? "")}`, undefined, e.timestamp);
    }

    case "delivery": {
      const delivered = String(e.status ?? "") !== "failed";
      const s: RunState = { ...state, delivery: { typing: false, linesShown: 5, delivered } };
      return pushLog(s, delivered ? "success" : "error",
        `delivery → ${String(e.destination)} ${delivered ? "delivered" : "failed"} ${String(e.message_url ?? "")}`,
        "post", e.timestamp);
    }

    case "run_complete": {
      const status = String(e.status ?? "complete");
      const s: RunState = { ...state, running: false, runStatus: "COMPLETE" };
      return pushLog(s, status === "error" ? "error" : "system", `run complete · ${status}`, undefined, e.timestamp);
    }

    default:
      return state;
  }
}
