import type { DeliveryState } from "@/lib/swarm/types";

interface Props { delivery: DeliveryState; }

const lines = [
  "*Design handoff · DesignSystem-v2*",
  "3 changed frames: Buttons/Primary, Icons/24px Set, Nav/Top Bar",
  "Specs: 2 colors · 2 spacing · 2 typography tokens",
  "Attached: icon-search@2x.png (48×48)",
  "→ Ready for implementation",
];

export function DeliveryPanel({ delivery }: Props) {
  return (
    <div className="panel flex min-h-0 flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Delivery</h2>
        <div className="flex items-center gap-1.5">
          {delivery.delivered && (
            <span className="flex items-center gap-1 text-[11px] font-medium text-success">
              <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none">
                <path d="M2 6.5L5 9L10 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              delivered
            </span>
          )}
        </div>
      </div>

      <div className="rounded-md border border-hairline bg-surface-2 p-3">
        <div className="flex items-start gap-3">
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded bg-selection/15 font-mono text-[11px] text-selection font-semibold">
            FS
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-1.5">
              <span className="text-[12px] font-semibold text-foreground">Figma Swarm Bot</span>
              <span className="font-mono text-[9px] text-muted-foreground">APP</span>
              <span className="font-mono text-[10px] text-muted-foreground">· #design-handoff · now</span>
            </div>
            <div className="mt-1 space-y-1">
              {lines.slice(0, delivery.linesShown).map((l, i) => (
                <div key={i} className="slide-in font-mono text-[11px] text-foreground/90">
                  {l}
                </div>
              ))}
              {delivery.typing && delivery.linesShown < lines.length && (
                <div className="flex items-center gap-1">
                  <span className="h-1 w-1 rounded-full bg-muted-foreground pulse-dot" />
                  <span className="h-1 w-1 rounded-full bg-muted-foreground pulse-dot" style={{ animationDelay: "0.15s" }} />
                  <span className="h-1 w-1 rounded-full bg-muted-foreground pulse-dot" style={{ animationDelay: "0.3s" }} />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
