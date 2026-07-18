import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import type { AgentId, RunState, LogEntry, LogSeverity, Spec, Mode } from "./types";
import { createInitialState } from "./initial-state";

type Action =
  | { type: "RESET"; runNumber?: number }
  | { type: "SET_MODE"; mode: Mode }
  | { type: "SET_SPEED"; speed: 1 | 2 }
  | { type: "START" }
  | { type: "STOP" }
  | { type: "RUN_STATUS"; status: RunState["runStatus"] }
  | { type: "AGENT"; id: AgentId; patch: Partial<RunState["agents"]["detect"]> }
  | { type: "TICK_SPARKS" }
  | { type: "HANDOFF"; from: AgentId; to: AgentId; payload: string }
  | { type: "HANDOFF_END" }
  | { type: "CHECKPOINT"; pct: number; ts: number }
  | { type: "LOG"; entry: Omit<LogEntry, "id"> }
  | { type: "SPEC"; spec: Spec }
  | { type: "ASSET_LOADING" }
  | { type: "ASSET_READY" }
  | { type: "FRAME"; id: string; patch: Partial<RunState["frames"][number]> }
  | { type: "FRAMES_ALL"; patch: Partial<RunState["frames"][number]> }
  | { type: "CURSOR"; x: number; y: number; caption?: string }
  | { type: "CURSOR_CLICK" }
  | { type: "TOAST"; text: string | null }
  | { type: "DELIVERY"; patch: Partial<RunState["delivery"]> }
  | { type: "LEARNED_MATCH"; index: number; matched: boolean };

let logCounter = 1;

function reducer(state: RunState, a: Action): RunState {
  switch (a.type) {
    case "RESET": {
      const base = createInitialState(a.runNumber ?? state.runNumber);
      return { ...base, speed: state.speed, mode: state.mode };
    }
    case "SET_MODE":
      return { ...createInitialState(state.runNumber), speed: state.speed, mode: a.mode };
    case "SET_SPEED":
      return { ...state, speed: a.speed };
    case "START":
      return { ...state, running: true, runStatus: "RUNNING" };
    case "STOP":
      return { ...state, running: false };
    case "RUN_STATUS":
      return { ...state, runStatus: a.status };
    case "AGENT":
      return {
        ...state,
        agents: {
          ...state.agents,
          [a.id]: { ...state.agents[a.id], ...a.patch },
        },
      };
    case "TICK_SPARKS": {
      const bump = (id: AgentId) => {
        const cur = state.agents[id];
        const active = cur.status === "active" || cur.status === "handoff";
        const next = active ? 0.55 + Math.random() * 0.45 : 0.12 + Math.random() * 0.15;
        return { ...cur, sparkline: [...cur.sparkline.slice(1), next] };
      };
      return {
        ...state,
        agents: { detect: bump("detect"), extract: bump("extract"), post: bump("post") },
      };
    }
    case "HANDOFF":
      return {
        ...state,
        handoff: { from: a.from, to: a.to, payload: a.payload, active: true, key: Date.now() },
      };
    case "HANDOFF_END":
      return { ...state, handoff: null };
    case "CHECKPOINT":
      return {
        ...state,
        checkpoints: state.checkpoints.map((c, i, arr) => {
          if (c.pct === a.pct) return { ...c, done: true, active: true, ts: a.ts };
          const idx = arr.findIndex((x) => x.pct === a.pct);
          if (i < idx) return { ...c, active: false, done: true };
          return { ...c, active: false };
        }),
      };
    case "LOG":
      return {
        ...state,
        logs: [...state.logs, { ...a.entry, id: logCounter++ }].slice(-120),
      };
    case "SPEC":
      return { ...state, specs: [...state.specs, a.spec] };
    case "ASSET_LOADING":
      return { ...state, asset: { filename: "icon-search@2x.png", width: 48, height: 48, ready: false } };
    case "ASSET_READY":
      return { ...state, asset: state.asset ? { ...state.asset, ready: true } : state.asset };
    case "FRAME":
      return {
        ...state,
        frames: state.frames.map((f) => (f.id === a.id ? { ...f, ...a.patch } : f)),
      };
    case "FRAMES_ALL":
      return { ...state, frames: state.frames.map((f) => ({ ...f, ...a.patch })) };
    case "CURSOR":
      return { ...state, cursor: { x: a.x, y: a.y, caption: a.caption } };
    case "CURSOR_CLICK":
      return { ...state, clickPulseKey: state.clickPulseKey + 1 };
    case "TOAST":
      return { ...state, toast: a.text };
    case "DELIVERY":
      return { ...state, delivery: { ...state.delivery, ...a.patch } };
    case "LEARNED_MATCH":
      return {
        ...state,
        learned: state.learned.map((l, i) => (i === a.index ? { ...l, matchedNow: a.matched } : l)),
      };
    default:
      return state;
  }
}

// ------- Mock event driver -------
// This is the SINGLE seam that would be replaced by a real WebSocket/API driver.
// Everything above is pure state; everything below is timed choreography.

type Dispatch = React.Dispatch<Action>;
type Step = (d: Dispatch, getState: () => RunState) => Promise<void> | void;

const now = () => performance.now();

function makeSleeper(getSpeed: () => 1 | 2) {
  return (ms: number) => new Promise<void>((r) => setTimeout(r, ms / getSpeed()));
}

function log(d: Dispatch, startedAt: number, severity: LogSeverity, text: string, agent?: AgentId) {
  d({ type: "LOG", entry: { t: now() - startedAt, severity, text, agent } });
}

export function useRunEngine() {
  const [state, dispatch] = useReducer(reducer, undefined, () => createInitialState(3));
  const abortRef = useRef<{ cancelled: boolean }>({ cancelled: false });
  const speedRef = useRef(state.speed);
  speedRef.current = state.speed;

  // Sparkline ticker
  useEffect(() => {
    const t = setInterval(() => dispatch({ type: "TICK_SPARKS" }), 350);
    return () => clearInterval(t);
  }, []);

  const cancel = useCallback(() => {
    abortRef.current.cancelled = true;
  }, []);

  const runChoreography = useCallback(async () => {
    const sleep = makeSleeper(() => speedRef.current);
    const startedAt = now();
    const token = abortRef.current;
    const guard = () => !token.cancelled;

    const cur = (x: number, y: number, caption?: string) =>
      dispatch({ type: "CURSOR", x, y, caption });
    const click = () => dispatch({ type: "CURSOR_CLICK" });

    // ---- Kickoff
    log(dispatch, startedAt, "system", "Swarm supervisor initialising · loading LangGraph state");
    await sleep(300); if (!guard()) return;

    // ---- Change Detection Agent
    dispatch({ type: "AGENT", id: "detect", patch: { status: "active", tool: "figma.get_file_versions" } });
    dispatch({ type: "CHECKPOINT", pct: 10, ts: now() - startedAt });
    log(dispatch, startedAt, "info", "change_detection: polling figma.get_file_versions", "detect");
    cur(20, 22, "Change Detection Agent → scanning file versions");
    await sleep(700); if (!guard()) return;

    if (state.mode === "no-changes") {
      // Alternate demo path
      log(dispatch, startedAt, "info", "change_detection: diffing against last known snapshot", "detect");
      await sleep(600);
      dispatch({ type: "FRAMES_ALL", patch: { skipped: true } });
      log(dispatch, startedAt, "success", "change_detection: 0 frames changed · no downstream work required", "detect");
      dispatch({ type: "AGENT", id: "detect", patch: { status: "done" } });
      // Fast-forward checkpoints to 100 with a special label
      dispatch({ type: "CHECKPOINT", pct: 30, ts: now() - startedAt });
      await sleep(200);
      dispatch({ type: "CHECKPOINT", pct: 100, ts: now() - startedAt });
      dispatch({ type: "RUN_STATUS", status: "COMPLETE" });
      log(dispatch, startedAt, "success", "run complete · No changes detected · no handoff required");
      dispatch({ type: "STOP" });
      return;
    }

    // Move cursor across each frame in layers panel
    for (const frame of state.frames) {
      if (!guard()) return;
      const y = 24 + state.frames.indexOf(frame) * 6;
      cur(14, y, `inspecting layer: ${frame.name}`);
      await sleep(280);
      if (frame.changed) {
        dispatch({ type: "FRAME", id: frame.id, patch: { highlighted: true } });
        log(dispatch, startedAt, "info", `change_detection: diff hit → ${frame.name}`, "detect");
      } else {
        dispatch({ type: "FRAME", id: frame.id, patch: { skipped: true } });
      }
    }

    log(dispatch, startedAt, "success", "change_detection: 3 changed frames identified", "detect");
    dispatch({ type: "CHECKPOINT", pct: 30, ts: now() - startedAt });
    dispatch({ type: "AGENT", id: "detect", patch: { status: "handoff" } });

    // Handoff detect → extract
    dispatch({ type: "HANDOFF", from: "detect", to: "extract", payload: "3 changed frames" });
    await sleep(1000); if (!guard()) return;
    dispatch({ type: "HANDOFF_END" });
    dispatch({ type: "AGENT", id: "detect", patch: { status: "done" } });

    // ---- Extraction Agent
    dispatch({ type: "AGENT", id: "extract", patch: { status: "active", tool: "figma.get_node" } });
    dispatch({ type: "CHECKPOINT", pct: 50, ts: now() - startedAt });
    log(dispatch, startedAt, "info", "extraction: opening changed frames via figma.get_node", "extract");

    // Click a changed frame in layers panel
    cur(14, 24, "Extraction Agent → selecting frame");
    await sleep(400);
    click();
    dispatch({ type: "FRAME", id: "f1", patch: { selected: true } });
    await sleep(400);

    // Hover properties inspector — flash values, add specs
    const specSteps: Array<{ x: number; y: number; caption: string; spec: Spec }> = [
      { x: 84, y: 26, caption: "Extraction Agent → reading spacing tokens",
        spec: { kind: "spacing", token: "space.md", px: 16 } },
      { x: 84, y: 36, caption: "Extraction Agent → reading spacing tokens",
        spec: { kind: "spacing", token: "space.lg", px: 24 } },
      { x: 84, y: 46, caption: "Extraction Agent → reading fill token",
        spec: { kind: "color", token: "color.primary", hex: "#7C5CFF" } },
      { x: 84, y: 56, caption: "Extraction Agent → reading fill token",
        spec: { kind: "color", token: "color.surface", hex: "#141416" } },
      { x: 84, y: 66, caption: "Extraction Agent → reading typography",
        spec: { kind: "type", token: "text.body", family: "Inter", weight: 500, size: 14 } },
      { x: 84, y: 76, caption: "Extraction Agent → reading typography",
        spec: { kind: "type", token: "text.h2", family: "Inter", weight: 600, size: 20 } },
    ];
    for (const s of specSteps) {
      if (!guard()) return;
      cur(s.x, s.y, s.caption);
      await sleep(320);
      dispatch({ type: "SPEC", spec: s.spec });
      log(dispatch, startedAt, "info",
        s.spec.kind === "color" ? `extraction: ${s.spec.token} = ${s.spec.hex}`
        : s.spec.kind === "spacing" ? `extraction: ${s.spec.token} = ${s.spec.px}px`
        : `extraction: ${s.spec.token} = ${s.spec.family} ${s.spec.weight}/${s.spec.size}`,
        "extract");
    }

    // Move to canvas icon, click, trigger export
    cur(52, 58, "Extraction Agent → selecting icon asset");
    await sleep(500);
    click();
    await sleep(200);
    dispatch({ type: "TOAST", text: "exporting asset…" });
    dispatch({ type: "ASSET_LOADING" });
    dispatch({ type: "AGENT", id: "extract", patch: { tool: "figma.export_image" } });
    log(dispatch, startedAt, "info", "extraction: figma.export_image → icon-search @2x", "extract");
    await sleep(500); if (!guard()) return;

    // ---- INJECTED FAILURE — pattern-matched self-heal
    log(dispatch, startedAt, "error", "figma.export_image → HTTP 429 rate limited", "extract");
    dispatch({ type: "AGENT", id: "extract", patch: { status: "error" } });
    dispatch({ type: "RUN_STATUS", status: "SELF-HEALING" });
    dispatch({ type: "LEARNED_MATCH", index: 1, matched: true });
    await sleep(500);
    log(dispatch, startedAt, "warn", "supervisor: pattern matched (run #2) → applying known fix: batched export + backoff", "extract");
    await sleep(600);
    log(dispatch, startedAt, "info", "extraction: retry #1 with 250ms backoff", "extract");
    await sleep(500);
    log(dispatch, startedAt, "success", "figma.export_image → 200 OK (icon-search@2x.png, 48×48)", "extract");
    dispatch({ type: "ASSET_READY" });
    dispatch({ type: "TOAST", text: null });
    dispatch({ type: "AGENT", id: "extract", patch: { status: "healed" } });
    dispatch({ type: "RUN_STATUS", status: "RUNNING" });
    await sleep(700);
    dispatch({ type: "LEARNED_MATCH", index: 1, matched: false });

    dispatch({ type: "CHECKPOINT", pct: 75, ts: now() - startedAt });
    dispatch({ type: "AGENT", id: "extract", patch: { status: "handoff" } });
    dispatch({ type: "HANDOFF", from: "extract", to: "post", payload: "specs + asset" });
    await sleep(1000); if (!guard()) return;
    dispatch({ type: "HANDOFF_END" });
    dispatch({ type: "AGENT", id: "extract", patch: { status: "done" } });

    // ---- Posting Agent
    dispatch({ type: "AGENT", id: "post", patch: { status: "active", tool: "slack.post_message" } });
    dispatch({ type: "CHECKPOINT", pct: 90, ts: now() - startedAt });
    log(dispatch, startedAt, "info", "posting: composing dev-ready summary", "post");
    cur(50, 88, "Posting Agent → composing Slack summary");
    dispatch({ type: "DELIVERY", patch: { typing: true, linesShown: 0, delivered: false } });
    for (let i = 1; i <= 5; i++) {
      if (!guard()) return;
      await sleep(280);
      dispatch({ type: "DELIVERY", patch: { linesShown: i } });
    }
    await sleep(300);
    dispatch({ type: "DELIVERY", patch: { typing: false, delivered: true } });
    log(dispatch, startedAt, "success", "slack.post_message → delivered to #design-handoff", "post");
    dispatch({ type: "CHECKPOINT", pct: 100, ts: now() - startedAt });
    dispatch({ type: "AGENT", id: "post", patch: { status: "done" } });
    dispatch({ type: "RUN_STATUS", status: "COMPLETE" });
    log(dispatch, startedAt, "system", "run complete · summary delivered");
    dispatch({ type: "STOP" });
  }, [state.mode, state.frames]);

  const start = useCallback(() => {
    abortRef.current = { cancelled: false };
    dispatch({ type: "RESET" });
    // give reducer a tick to reset before running
    setTimeout(() => {
      dispatch({ type: "START" });
      runChoreography();
    }, 20);
  }, [runChoreography]);

  const replay = useCallback(() => {
    cancel();
    setTimeout(() => start(), 50);
  }, [cancel, start]);

  const setMode = useCallback((mode: Mode) => {
    cancel();
    dispatch({ type: "SET_MODE", mode });
  }, [cancel]);

  const setSpeed = useCallback((s: 1 | 2) => dispatch({ type: "SET_SPEED", speed: s }), []);

  return useMemo(() => ({ state, start, replay, setMode, setSpeed }), [state, start, replay, setMode, setSpeed]);
}
