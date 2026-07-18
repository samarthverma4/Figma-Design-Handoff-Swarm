import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { AgentId, RunState, LogSeverity, Mode } from "./types";
import { createInitialState } from "./initial-state";
import { applyEvent, type WsEvent } from "./event-adapter";

/**
 * LIVE run engine — replaces the mock choreography in use-run-engine.ts.
 *
 * This is the "real WebSocket/API driver" the mock's comment referred to. It
 * connects to the Python backend, streams typed events over /ws/run, and pipes
 * them through the pure adapter (event-adapter.ts) to build the same RunState
 * the dashboard already consumes. `start()` triggers a genuine run via POST /run.
 */

function backendHttp(): string {
  if (typeof window !== "undefined") {
    const override = window.localStorage.getItem("swarm-backend");
    if (override) return override.replace(/\/$/, "");
  }
  return "http://localhost:8000";
}
function backendWs(): string {
  return backendHttp().replace(/^http/, "ws") + "/ws/run";
}

let connLogId = 100000;

type Action =
  | { type: "RESET"; runNumber?: number }
  | { type: "EVENT"; event: WsEvent }
  | { type: "TICK_SPARKS" }
  | { type: "CLEAR_HANDOFF" }
  | { type: "CONN"; text: string; severity: LogSeverity }
  | { type: "SET_SPEED"; speed: 1 | 2 }
  | { type: "SET_MODE"; mode: Mode };

function reducer(state: RunState, a: Action): RunState {
  switch (a.type) {
    case "RESET": {
      const base = createInitialState(a.runNumber ?? state.runNumber);
      return { ...base, speed: state.speed, mode: state.mode };
    }
    case "EVENT":
      return applyEvent(state, a.event);
    case "CLEAR_HANDOFF":
      return state.handoff ? { ...state, handoff: null } : state;
    case "CONN":
      return {
        ...state,
        logs: [...state.logs, { id: connLogId++, t: state.logs.at(-1)?.t ?? 0, severity: a.severity, text: a.text }].slice(-120),
      };
    case "SET_SPEED":
      return { ...state, speed: a.speed };
    case "SET_MODE":
      return { ...state, mode: a.mode };
    case "TICK_SPARKS": {
      const bump = (id: AgentId) => {
        const cur = state.agents[id];
        const active = cur.status === "active" || cur.status === "handoff" || cur.status === "error";
        const next = active ? 0.55 + Math.random() * 0.45 : 0.12 + Math.random() * 0.15;
        return { ...cur, sparkline: [...cur.sparkline.slice(1), next] };
      };
      return { ...state, agents: { detect: bump("detect"), extract: bump("extract"), post: bump("post") } };
    }
    default:
      return state;
  }
}

export function useLiveRunEngine() {
  const [state, dispatch] = useReducer(reducer, undefined, () => createInitialState(1));
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const handoffTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const t = setInterval(() => dispatch({ type: "TICK_SPARKS" }), 350);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      let ws: WebSocket;
      try {
        ws = new WebSocket(backendWs());
      } catch {
        retry = setTimeout(connect, 2000);
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        dispatch({ type: "CONN", text: "connected to swarm backend", severity: "system" });
      };
      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as WsEvent;
          dispatch({ type: "EVENT", event });
          if (event.type === "handoff") {
            if (handoffTimer.current) clearTimeout(handoffTimer.current);
            handoffTimer.current = setTimeout(() => dispatch({ type: "CLEAR_HANDOFF" }), 1400);
          }
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
    };
    connect();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      if (handoffTimer.current) clearTimeout(handoffTimer.current);
      wsRef.current?.close();
    };
  }, []);

  const start = useCallback(async () => {
    dispatch({ type: "RESET" });
    try {
      const res = await fetch(backendHttp() + "/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(`POST /run ${res.status}`);
    } catch (err) {
      dispatch({
        type: "CONN",
        text: `could not reach backend at ${backendHttp()} — is it running? (${String(err)})`,
        severity: "error",
      });
    }
  }, []);

  const replay = useCallback(() => {
    void start();
  }, [start]);
  const setMode = useCallback((mode: Mode) => dispatch({ type: "SET_MODE", mode }), []);
  const setSpeed = useCallback((s: 1 | 2) => dispatch({ type: "SET_SPEED", speed: s }), []);

  return useMemo(
    () => ({ state, start, replay, setMode, setSpeed, connected }),
    [state, start, replay, setMode, setSpeed, connected],
  );
}
