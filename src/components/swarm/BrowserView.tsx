import type { Frame, CursorTarget } from "@/lib/swarm/types";
import { GhostCursor } from "./GhostCursor";

interface Props {
  frames: Frame[];
  cursor: CursorTarget;
  clickPulseKey: number;
  toast: string | null;
}

export function BrowserView({ frames, cursor, clickPulseKey, toast }: Props) {
  return (
    <div className="panel flex h-full flex-col overflow-hidden">
      {/* Browser chrome */}
      <div className="flex items-center gap-2 border-b border-hairline bg-surface-2 px-3 py-2">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-error/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-warning/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-success/80" />
        </div>
        <div className="ml-3 flex-1">
          <div className="mx-auto max-w-md truncate rounded-md border border-hairline bg-background px-3 py-1 text-center font-mono text-[11px] text-muted-foreground">
            figma.com/file/DesignSystem-v2
          </div>
        </div>
      </div>

      {/* Figma editor mock */}
      <div className="relative flex-1 overflow-hidden bg-background">
        <div className="absolute inset-0 grid grid-cols-[26%_1fr_22%]">
          {/* Layers panel */}
          <div className="border-r border-hairline bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Layers</span>
              <span className="font-mono text-[10px] text-muted-foreground">v2.14</span>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-[11px] text-foreground/80">
                <span>▾</span><span className="font-medium">DesignSystem-v2</span>
              </div>
              <div className="ml-2 space-y-0.5">
                {frames.map((f) => (
                  <div
                    key={f.id}
                    className={`flex items-center justify-between rounded px-1.5 py-1 text-[11px] transition-all ${
                      f.selected ? "bg-primary/15 text-foreground" :
                      f.highlighted ? "bg-violet/10 text-foreground" :
                      f.skipped ? "opacity-40 text-muted-foreground" : "text-foreground/80"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 truncate">
                      <span
                        className="h-1.5 w-1.5 rounded-sm"
                        style={{ backgroundColor: f.selected ? "var(--violet)" : f.highlighted ? "var(--violet)" : "var(--muted-foreground)" }}
                      />
                      <span className="truncate font-mono">{f.name}</span>
                    </div>
                    {f.skipped && (
                      <span className="font-mono text-[9px] uppercase text-muted-foreground">skipped</span>
                    )}
                    {f.changed && !f.skipped && (
                      <span className="font-mono text-[9px] uppercase" style={{ color: "var(--violet)" }}>changed</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Canvas */}
          <div className="relative overflow-hidden bg-[color:var(--surface-2)]">
            <div
              className="absolute inset-0 opacity-40"
              style={{
                backgroundImage:
                  "radial-gradient(circle at 1px 1px, var(--hairline) 1px, transparent 0)",
                backgroundSize: "18px 18px",
              }}
            />
            <div className="relative grid h-full grid-cols-2 gap-4 p-6">
              {/* Frame: buttons */}
              <CanvasFrame frame={frames[0]} label="Buttons / Primary">
                <div className="flex flex-wrap gap-2">
                  <div className="rounded-md bg-primary px-3 py-1.5 text-[10px] text-primary-foreground">Primary</div>
                  <div className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-[10px] text-foreground">Ghost</div>
                  <div className="rounded-md bg-surface-3 px-3 py-1.5 text-[10px] text-foreground">Secondary</div>
                </div>
              </CanvasFrame>
              {/* Frame: card */}
              <CanvasFrame frame={frames[1]} label="Card / Product">
                <div className="space-y-1.5">
                  <div className="h-6 w-full rounded bg-surface-3" />
                  <div className="h-1.5 w-3/4 rounded bg-hairline" />
                  <div className="h-1.5 w-1/2 rounded bg-hairline" />
                </div>
              </CanvasFrame>
              {/* Frame: icons */}
              <CanvasFrame frame={frames[2]} label="Icons / 24px Set">
                <div className="grid grid-cols-4 gap-2">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="flex h-6 w-6 items-center justify-center rounded border border-hairline bg-surface">
                      <div className="h-2.5 w-2.5 rounded-sm bg-foreground/60" />
                    </div>
                  ))}
                </div>
              </CanvasFrame>
              {/* Frame: nav */}
              <CanvasFrame frame={frames[3]} label="Nav / Top Bar">
                <div className="flex items-center justify-between rounded bg-surface p-1.5">
                  <div className="h-2 w-8 rounded bg-primary" />
                  <div className="flex gap-1.5">
                    <div className="h-1.5 w-6 rounded bg-hairline" />
                    <div className="h-1.5 w-6 rounded bg-hairline" />
                    <div className="h-1.5 w-6 rounded bg-hairline" />
                  </div>
                </div>
              </CanvasFrame>
            </div>

            {/* Toast */}
            {toast && (
              <div className="slide-in shadow-float absolute bottom-3 right-3 flex items-center gap-2 rounded-lg border border-hairline bg-surface px-3 py-2 text-[12px] backdrop-blur">
                <span className="h-1.5 w-1.5 rounded-full bg-violet pulse-dot" />
                <span className="font-mono text-foreground">{toast}</span>
              </div>
            )}
          </div>

          {/* Properties inspector */}
          <div className="border-l border-hairline bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Design</span>
            </div>
            <PropSection label="Auto layout">
              <PropRow k="padding-x" v="16" />
              <PropRow k="padding-y" v="24" />
              <PropRow k="gap" v="8" />
            </PropSection>
            <PropSection label="Fill">
              <PropSwatch color="#7C5CFF" name="color.primary" />
              <PropSwatch color="#141416" name="color.surface" />
            </PropSection>
            <PropSection label="Typography">
              <PropRow k="family" v="Inter" />
              <PropRow k="weight" v="500 · 14" />
              <PropRow k="line-h" v="1.4" />
            </PropSection>
          </div>
        </div>

        <GhostCursor target={cursor} pulseKey={clickPulseKey} />
      </div>
    </div>
  );
}

function CanvasFrame({ frame, label, children }: { frame: Frame; label: string; children: React.ReactNode }) {
  const selected = frame.selected;
  const skipped = frame.skipped;
  return (
    <div className="relative flex min-h-0 flex-col">
      <div className="mb-1 font-mono text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div
        className={`relative flex-1 rounded-md border p-3 transition-all ${
          selected ? "border-selection" : "border-hairline"
        } ${skipped ? "opacity-30" : ""} bg-surface`}
        style={selected ? { boxShadow: "0 0 0 1px hsl(204 100% 52.4% / 0.4)" } : undefined}
      >
        {children}
        {selected && (
          <>
            {["-top-1 -left-1", "-top-1 -right-1", "-bottom-1 -left-1", "-bottom-1 -right-1"].map((p) => (
              <span key={p} className={`absolute ${p} h-2 w-2 border border-selection bg-background`} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function PropSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3 border-t border-hairline pt-2 first:border-t-0 first:pt-0">
      <div className="mb-1.5 font-mono text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}
function PropRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between font-mono text-[10px]">
      <span className="text-muted-foreground">{k}</span>
      <span className="text-foreground">{v}</span>
    </div>
  );
}
function PropSwatch({ color, name }: { color: string; name: string }) {
  return (
    <div className="flex items-center justify-between font-mono text-[10px]">
      <div className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm border border-hairline" style={{ backgroundColor: color }} />
        <span className="text-muted-foreground">{name}</span>
      </div>
      <span className="text-foreground">{color}</span>
    </div>
  );
}
