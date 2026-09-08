import type { Checkpoint } from "@/lib/swarm/types";

interface Props { checkpoints: Checkpoint[]; }

export function ProgressRail({ checkpoints }: Props) {
  const activeIdx = checkpoints.findIndex((c) => c.active);
  const lastDoneIdx = checkpoints.map((c) => c.done).lastIndexOf(true);
  const currentIdx = activeIdx >= 0 ? activeIdx : lastDoneIdx;
  const current = currentIdx >= 0 ? checkpoints[currentIdx] : null;

  return (
    <div className="panel px-4 py-3">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Run Progress</span>
        {current && (
          <span className="text-[12px]">
            <span className="text-selection font-medium">{current.pct}%</span>
            <span className="text-muted-foreground"> · {current.label}</span>
          </span>
        )}
      </div>
      <div className="relative">
        <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-px bg-hairline" />
        <div
          className="absolute left-0 top-1/2 -translate-y-1/2 h-px bg-selection transition-all duration-500"
          style={{ width: `${current ? current.pct : 0}%` }}
        />
        <div className="relative flex justify-between">
          {checkpoints.map((c) => (
            <div key={c.pct} className="flex flex-col items-center gap-1.5" style={{ width: 0 }}>
              <div className="relative flex h-3 w-3 items-center justify-center">
                <div
                  className={`h-3 w-3 rounded-full border-2 transition-all ${
                    c.done ? "border-selection bg-selection" :
                    c.active ? "border-selection bg-background pulse-dot" :
                    "border-hairline-strong bg-background"
                  }`}
                />
                {c.done && (
                  <svg className="absolute h-2 w-2 text-white" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6.5L5 9L10 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
              <span className="font-mono text-[10px] text-muted-foreground">{c.pct}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
