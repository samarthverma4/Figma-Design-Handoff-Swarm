import type { Mode, RunStatus } from "@/lib/swarm/types";

const stack = ["Figma MCP"];

const statusColor: Record<RunStatus, string> = {
  IDLE: "text-muted-foreground",
  RUNNING: "text-selection",
  "SELF-HEALING": "text-warning",
  COMPLETE: "text-success",
};
const statusDot: Record<RunStatus, string> = {
  IDLE: "bg-muted-foreground",
  RUNNING: "bg-selection",
  "SELF-HEALING": "bg-warning",
  COMPLETE: "bg-success",
};

interface Props {
  runStatus: RunStatus;
  runNumber: number;
  mode: Mode;
  onToggleMode: (m: Mode) => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
}

function SunIcon() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="8" r="2.75" />
      <path d="M8 1.5v1.5M8 13v1.5M1.5 8h1.5M13 8h1.5M3.3 3.3l1 1M11.7 11.7l1 1M3.3 12.7l1-1M11.7 4.3l1-1" />
    </svg>
  );
}
function MoonIcon() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="currentColor">
      <path d="M6.5 2a5.75 5.75 0 007.5 7.5 6 6 0 11-7.5-7.5z" />
    </svg>
  );
}

export function TopBar({ runStatus, runNumber, mode, onToggleMode, theme, onToggleTheme }: Props) {
  return (
    <header
      className="flex items-center justify-between border-b border-hairline bg-surface px-6 py-3"
      style={{ boxShadow: "var(--shadow-resting)" }}
    >
      <div className="flex items-center gap-3">
        <h1 className="text-[15px] font-semibold tracking-tight text-foreground">
          Figma Design Handoff Swarm
        </h1>
      </div>
      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-1.5 md:flex">
          {stack.map((s) => (
            <span
              key={s}
              className="font-mono text-[11px] tracking-wider text-muted-foreground rounded-md border border-hairline bg-surface-alt px-2 py-1"
              style={{ backgroundColor: "var(--surface-alt)" }}
            >
              {s}
            </span>
          ))}
        </div>
        <div className="mx-2 h-6 w-px bg-hairline" />
        <button
          onClick={() => onToggleMode(mode === "changes" ? "no-changes" : "changes")}
          className="font-mono text-[11px] uppercase tracking-wider rounded-md border border-hairline bg-surface-2 px-2.5 py-1.5 text-muted-foreground hover:text-foreground hover:border-hairline-strong transition-colors"
          title="Toggle demo scenario"
        >
          mode: {mode === "changes" ? "changes" : "no-edits"}
        </button>
        <div className="flex items-center gap-2 rounded-md border border-hairline bg-surface-2 px-3 py-1.5">
          <span className={`h-1.5 w-1.5 rounded-full pulse-dot ${statusDot[runStatus]}`} />
          <span className={`text-[12px] font-medium ${statusColor[runStatus]}`}>{runStatus}</span>
          <span className="font-mono text-[11px] text-muted-foreground">· Run #{runNumber}</span>
        </div>
        <button
          onClick={onToggleTheme}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-hairline bg-surface-2 text-muted-foreground hover:text-foreground hover:border-hairline-strong transition-colors"
          title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
      </div>
    </header>
  );
}
