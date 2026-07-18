import type { RunState, Frame, LearnedPattern } from "./types";

export const initialFrames: Frame[] = [
  { id: "f1", name: "Buttons / Primary", changed: true, highlighted: false, selected: false, skipped: false },
  { id: "f2", name: "Card / Product", changed: false, highlighted: false, selected: false, skipped: false },
  { id: "f3", name: "Icons / 24px Set", changed: true, highlighted: false, selected: false, skipped: false },
  { id: "f4", name: "Nav / Top Bar", changed: true, highlighted: false, selected: false, skipped: false },
  { id: "f5", name: "Modal / Confirm", changed: false, highlighted: false, selected: false, skipped: false },
];

export const learnedPatterns: LearnedPattern[] = [
  {
    runNumber: 1,
    failure: "nested auto-layout frame returned null spacing",
    resolution: "falls back to bounding-box measurement",
  },
  {
    runNumber: 2,
    failure: "export rate limit at >5 concurrent requests",
    resolution: "batches exports with exponential backoff",
  },
];

export const createInitialState = (runNumber = 3): RunState => ({
  mode: "changes",
  runNumber,
  runStatus: "IDLE",
  speed: 1,
  running: false,
  agents: {
    detect: {
      id: "detect",
      name: "Change Detection Agent",
      color: "blue",
      status: "idle",
      tool: "figma.get_file_versions",
      sparkline: Array.from({ length: 24 }, () => 0.2 + Math.random() * 0.2),
    },
    extract: {
      id: "extract",
      name: "Extraction Agent",
      color: "violet",
      status: "idle",
      tool: "figma.get_node",
      sparkline: Array.from({ length: 24 }, () => 0.2 + Math.random() * 0.2),
    },
    post: {
      id: "post",
      name: "Posting Agent",
      color: "green",
      status: "idle",
      tool: "slack.post_message",
      sparkline: Array.from({ length: 24 }, () => 0.2 + Math.random() * 0.2),
    },
  },
  handoff: null,
  checkpoints: [
    { pct: 10, label: "Change detection started", done: false, active: false },
    { pct: 30, label: "Change detection complete · 3 frames changed", done: false, active: false },
    { pct: 50, label: "Extraction in progress", done: false, active: false },
    { pct: 75, label: "Specs extracted · asset exported", done: false, active: false },
    { pct: 90, label: "Posting to Slack", done: false, active: false },
    { pct: 100, label: "Summary posted · run complete", done: false, active: false },
  ],
  logs: [],
  specs: [],
  asset: null,
  frames: initialFrames.map((f) => ({ ...f })),
  cursor: { x: 50, y: 50 },
  clickPulseKey: 0,
  toast: null,
  learned: learnedPatterns.map((p) => ({ ...p })),
  delivery: { typing: false, linesShown: 0, delivered: false },
});
