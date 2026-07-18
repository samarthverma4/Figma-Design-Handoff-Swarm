import type { Spec, AssetExport } from "@/lib/swarm/types";

interface Props { specs: Spec[]; asset: AssetExport | null; }

export function ExtractionPanel({ specs, asset }: Props) {
  return (
    <div className="panel flex min-h-0 flex-col p-3.5">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Extraction Output</h2>
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {specs.length} specs
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-1">
        {specs.length === 0 && (
          <div className="rounded border border-dashed border-hairline p-3 text-center font-mono text-[10px] text-muted-foreground">
            waiting for extraction agent…
          </div>
        )}
        {specs.map((s, i) => (
          <SpecRow key={i} spec={s} />
        ))}
      </div>

      <div className="mt-3 border-t border-hairline pt-3">
        <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Exported Asset</div>
        {asset ? (
          <div className="slide-in flex items-center gap-3 rounded-md border border-hairline bg-surface-2 p-2.5">
            <div className="relative h-12 w-12 overflow-hidden rounded border border-hairline">
              {!asset.ready ? (
                <div className="shimmer h-full w-full" />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-surface">
                  <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7 text-foreground/80">
                    <circle cx="11" cy="11" r="6" stroke="currentColor" strokeWidth="1.75" />
                    <path d="M20 20L16 16" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
                  </svg>
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="truncate font-mono text-[11px] text-foreground">{asset.filename}</div>
              <div className="font-mono text-[10px] text-muted-foreground">
                {asset.width} × {asset.height} · {asset.ready ? "ready" : "exporting…"}
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded border border-dashed border-hairline p-3 text-center font-mono text-[10px] text-muted-foreground">
            no assets yet
          </div>
        )}
      </div>
    </div>
  );
}

function SpecRow({ spec }: { spec: Spec }) {
  if (spec.kind === "color") {
    return (
      <div className="slide-in flex items-center justify-between rounded border border-hairline bg-surface-2 px-2.5 py-1.5">
        <div className="flex items-center gap-2">
          <span className="h-4 w-4 rounded-sm border border-hairline" style={{ backgroundColor: spec.hex }} />
          <span className="font-mono text-[11px] text-foreground">{spec.token}</span>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">{spec.hex}</span>
      </div>
    );
  }
  if (spec.kind === "spacing") {
    const w = Math.min(60, spec.px * 2);
    return (
      <div className="slide-in flex items-center justify-between rounded border border-hairline bg-surface-2 px-2.5 py-1.5">
        <div className="flex items-center gap-2">
          <div className="h-1 rounded bg-primary" style={{ width: `${w}px` }} />
          <span className="font-mono text-[11px] text-foreground">{spec.token}</span>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">{spec.px}px</span>
      </div>
    );
  }
  return (
    <div className="slide-in flex items-center justify-between rounded border border-hairline bg-surface-2 px-2.5 py-1.5">
      <div className="flex items-center gap-2">
        <span
          className="text-foreground"
          style={{ fontFamily: spec.family, fontWeight: spec.weight, fontSize: `${Math.min(14, spec.size)}px` }}
        >
          Aa
        </span>
        <span className="font-mono text-[11px] text-foreground">{spec.token}</span>
      </div>
      <span className="font-mono text-[10px] text-muted-foreground">
        {spec.family} · {spec.weight}/{spec.size}
      </span>
    </div>
  );
}
