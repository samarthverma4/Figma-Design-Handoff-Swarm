import { useEffect, useRef } from "react";
import type { LogEntry, LearnedPattern } from "@/lib/swarm/types";

const sevColor: Record<LogEntry["severity"], string> = {
  info: "text-foreground/85",
  warn: "text-warning",
  error: "text-error",
  success: "text-success",
  system: "text-selection",
};
const sevTag: Record<LogEntry["severity"], string> = {
  info: "INFO",
  warn: "WARN",
  error: "ERR ",
  success: " OK ",
  system: "SYS ",
};

function fmtTime(ms: number) {
  const s = (ms / 1000).toFixed(2);
  return s.padStart(6, "0") + "s";
}

interface Props { logs: LogEntry[]; learned: LearnedPattern[]; }

export function Console({ logs, learned }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs.length]);

  return (
    <div className="panel grid h-full grid-cols-[1fr_320px] overflow-hidden">
      <div className="flex min-h-0 flex-col border-r border-hairline">
        <div className="flex items-center justify-between border-b border-hairline bg-surface-2 px-3 py-2">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Self-Healing Console</span>
          </div>
          <span className="font-mono text-[11px] text-muted-foreground">{logs.length} lines</span>
        </div>
        <div ref={ref} className="flex-1 min-h-0 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed">
          {logs.length === 0 && (
            <div className="text-muted-foreground/70">// idle · awaiting run</div>
          )}
          {logs.map((l) => (
            <div key={l.id} className="flex gap-3">
              <span className="text-muted-foreground/70">{fmtTime(l.t)}</span>
              <span className={sevColor[l.severity]}>[{sevTag[l.severity]}]</span>
              {l.agent && <span className="text-muted-foreground">{l.agent}</span>}
              <span className={sevColor[l.severity]}>{l.text}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-col">
        <div className="border-b border-hairline bg-surface-2 px-3 py-2">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Learned Patterns · persistent memory</span>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-2">
          {learned.map((p, i) => (
            <div
              key={i}
              className={`rounded-md border p-3 transition-all ${
                p.matchedNow ? "border-selection bg-selection/5" : "border-hairline bg-surface-2"
              }`}
              style={p.matchedNow ? { boxShadow: "0 0 0 1px hsl(204 100% 52.4% / 0.35)" } : undefined}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Run #{p.runNumber}</span>
                {p.matchedNow && <span className="text-[10px] font-medium uppercase tracking-wider text-selection">pattern matched</span>}
              </div>
              <div className="mt-1 font-mono text-[11px] text-error">↳ {p.failure}</div>
              <div className="mt-0.5 font-mono text-[11px] text-success">✓ {p.resolution}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
