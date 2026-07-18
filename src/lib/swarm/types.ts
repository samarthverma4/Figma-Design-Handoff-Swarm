export type AgentId = "detect" | "extract" | "post";
export type AgentStatus = "idle" | "active" | "handoff" | "error" | "healed" | "done" | "skipped";
export type RunStatus = "IDLE" | "RUNNING" | "SELF-HEALING" | "COMPLETE";
export type Mode = "changes" | "no-changes";

export interface AgentState {
  id: AgentId;
  name: string;
  color: "blue" | "violet" | "green";
  status: AgentStatus;
  tool: string;
  sparkline: number[];
}

export type LogSeverity = "info" | "warn" | "error" | "success" | "system";
export interface LogEntry {
  id: number;
  t: number; // ms since run start
  severity: LogSeverity;
  agent?: AgentId;
  text: string;
}

export interface Checkpoint {
  pct: number;
  label: string;
  done: boolean;
  active: boolean;
  ts?: number;
}

export interface SpecColor { kind: "color"; token: string; hex: string; }
export interface SpecSpacing { kind: "spacing"; token: string; px: number; }
export interface SpecType { kind: "type"; token: string; family: string; weight: number; size: number; }
export type Spec = SpecColor | SpecSpacing | SpecType;

export interface AssetExport {
  filename: string;
  width: number;
  height: number;
  ready: boolean;
}

export interface Frame {
  id: string;
  name: string;
  changed: boolean;
  highlighted: boolean;
  selected: boolean;
  skipped: boolean;
}

export interface LearnedPattern {
  runNumber: number;
  failure: string;
  resolution: string;
  matchedNow?: boolean;
}

export interface Handoff {
  from: AgentId;
  to: AgentId;
  payload: string;
  active: boolean;
  key: number;
}

export interface CursorTarget {
  x: number; // 0..100 (% of browser viewport)
  y: number;
  click?: boolean;
  caption?: string;
}

export interface DeliveryState {
  typing: boolean;
  linesShown: number;
  delivered: boolean;
}

export interface RunState {
  mode: Mode;
  runNumber: number;
  runStatus: RunStatus;
  speed: 1 | 2;
  agents: Record<AgentId, AgentState>;
  handoff: Handoff | null;
  checkpoints: Checkpoint[];
  logs: LogEntry[];
  specs: Spec[];
  asset: AssetExport | null;
  frames: Frame[];
  cursor: CursorTarget;
  clickPulseKey: number;
  toast: string | null;
  learned: LearnedPattern[];
  delivery: DeliveryState;
  running: boolean;
}
